"""
src/storage/chroma_store.py

Persistent vector store. Each upload session gets its own ChromaDB
collection, so documents from different sessions never mix.
"""
import logging
import threading
import time

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


class ChromaStore:
    def __init__(self, persist_dir: str = "outputs/chroma"):
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        # Guards the read-count-then-assign-ids sequence in add() against
        # two concurrent ingests into the same session computing the same
        # id range, and (G27) the content-hash-exists-check-then-add
        # sequence that de-duplicates re-uploaded content — both need to
        # be atomic relative to other adds into the same session. Only
        # protects this single process — a multi-worker deployment would
        # need a cross-process lock instead.
        self._add_lock = threading.Lock()

    def get_or_create_collection(self, session_id: str):
        now = time.time()
        return self.client.get_or_create_collection(
            name=f"session_{session_id}",
            # metadata= is only honored on first creation — chromadb
            # silently ignores it on a subsequent get_or_create against an
            # existing collection (confirmed against 1.5.9), so a session's
            # last_activity_at must be advanced separately via
            # _touch_activity()/collection.modify(). created_at and
            # last_activity_at start equal (G10 R5): a session that's never
            # touched again still expires at ttl_hours from creation.
            metadata={"hnsw:space": "cosine", "created_at": now, "last_activity_at": now},
        )

    def _touch_activity(self, collection) -> None:
        """Advances a collection's last_activity_at to now (G10 R1).
        collection.modify() replaces its metadata wholesale rather than
        merging, so the existing metadata is read and merged in here —
        a naive metadata={"last_activity_at": ...} call would silently
        drop created_at. hnsw:space must be dropped before the call:
        chromadb rejects any modify() whose metadata contains that key
        at all, even unchanged ("Changing the distance function of a
        collection once it is created is not supported currently") —
        confirmed against 1.5.9. It's fixed at creation regardless, so
        omitting it here loses nothing but its mirror in .metadata."""
        metadata = dict(collection.metadata or {})
        metadata.pop("hnsw:space", None)
        metadata["last_activity_at"] = time.time()
        collection.modify(metadata=metadata)

    def add(self, session_id: str, chunks: list, embeddings: list, metadatas: list) -> set:
        """Adds chunks to a session's collection, skipping any whose
        `content_hash` metadata already has a chunk stored in this
        session (G27 dedup — a re-uploaded file's content is not stored
        twice). A chunk with no `content_hash` key is always added,
        preserving the old unconditional-append behavior for any caller
        that doesn't stamp one. Chunks that share a hash with an earlier
        chunk in this same call are also treated as duplicates of that
        earlier chunk, so uploading identical content twice in one
        request is caught even though neither copy is in the collection
        yet when this call starts.

        Returns the set of `content_hash` values that were newly added
        by this call (empty if every hash present was already indexed).
        """
        with self._add_lock:
            collection = self.get_or_create_collection(session_id)

            # First pass: decide, per unique hash, whether it's new to
            # this session. Chunks with no hash are always kept and never
            # consulted here.
            newly_added_hashes = set()
            rejected_hashes = set()
            for meta in metadatas:
                content_hash = meta.get("content_hash")
                if content_hash is None:
                    continue
                if content_hash in newly_added_hashes or content_hash in rejected_hashes:
                    continue
                existing_match = collection.get(
                    where={"content_hash": content_hash}, limit=1, include=[]
                )
                if existing_match["ids"]:
                    rejected_hashes.add(content_hash)
                else:
                    newly_added_hashes.add(content_hash)

            # Second pass: keep every hash-less chunk, plus every chunk
            # whose hash was decided "new" above.
            keep = [
                i
                for i, meta in enumerate(metadatas)
                if meta.get("content_hash") is None
                or meta.get("content_hash") in newly_added_hashes
            ]

            if keep:
                # offset new ids by current collection size so append-to-
                # existing-session uploads don't collide with previously
                # ingested chunks
                existing_count = collection.count()
                ids = [f"{session_id}_{existing_count + i}" for i in range(len(keep))]
                collection.add(
                    documents=[chunks[i] for i in keep],
                    embeddings=[embeddings[i] for i in keep],
                    metadatas=[metadatas[i] for i in keep],
                    ids=ids,
                )
            self._touch_activity(collection)
            return newly_added_hashes

    def query(self, session_id: str, query_embedding: list, top_k: int = 5) -> dict:
        collection = self.client.get_collection(f"session_{session_id}")
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, max(collection.count(), 1)),
            include=["documents", "metadatas", "distances"],
        )
        # A session already deleted by cleanup_expired raises above and
        # never reaches this line, so a query can't resurrect a dead
        # session's liveness (G10 R7).
        self._touch_activity(collection)
        return result

    def session_exists(self, session_id: str) -> bool:
        try:
            return self.client.get_collection(f"session_{session_id}").count() > 0
        except chromadb.errors.NotFoundError:
            return False

    def delete_session(self, session_id: str) -> bool:
        try:
            self.client.delete_collection(f"session_{session_id}")
            return True
        except chromadb.errors.NotFoundError:
            return False

    def cleanup_expired(self, ttl_hours: int, max_lifetime_hours: int) -> int:
        """Delete a collection once EITHER window elapses (G10): idle for
        more than ttl_hours since its last activity, or older than
        max_lifetime_hours since creation regardless of activity. Call
        periodically (e.g. from a cron/scheduled task) to stop storage
        from growing forever on a free-tier disk."""
        now = time.time()
        idle_cutoff = now - ttl_hours * 3600
        lifetime_cutoff = now - max_lifetime_hours * 3600
        deleted = 0
        for coll in self.client.list_collections():
            metadata = coll.metadata or {}
            created_at = metadata.get("created_at")
            # Collections stored before this change ships have no
            # last_activity_at yet — fall back to created_at so they
            # still expire under the idle-timeout rule.
            last_activity_at = metadata.get("last_activity_at", created_at)
            idle_expired = last_activity_at is not None and last_activity_at < idle_cutoff
            lifetime_expired = created_at is not None and created_at < lifetime_cutoff
            if idle_expired or lifetime_expired:
                self.client.delete_collection(coll.name)
                deleted += 1
        if deleted:
            logger.info("Cleanup: removed %d expired session(s)", deleted)
        return deleted
