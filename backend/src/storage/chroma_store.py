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
        # id range. Only protects this single process — a multi-worker
        # deployment would need a cross-process lock instead.
        self._add_lock = threading.Lock()

    def get_or_create_collection(self, session_id: str):
        return self.client.get_or_create_collection(
            name=f"session_{session_id}",
            metadata={"hnsw:space": "cosine", "created_at": time.time()},
        )

    def add(self, session_id: str, chunks: list, embeddings: list, metadatas: list) -> None:
        with self._add_lock:
            collection = self.get_or_create_collection(session_id)
            # offset new ids by current collection size so append-to-existing-
            # session uploads don't collide with previously ingested chunks
            existing = collection.count()
            ids = [f"{session_id}_{existing + i}" for i in range(len(chunks))]
            collection.add(documents=chunks, embeddings=embeddings, metadatas=metadatas, ids=ids)

    def query(self, session_id: str, query_embedding: list, top_k: int = 5) -> dict:
        collection = self.client.get_collection(f"session_{session_id}")
        return collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, max(collection.count(), 1)),
            include=["documents", "metadatas", "distances"],
        )

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

    def cleanup_expired(self, ttl_hours: int) -> int:
        """Delete collections older than ttl_hours. Call periodically
        (e.g. from a cron/scheduled task) to stop storage from growing
        forever on a free-tier disk."""
        cutoff = time.time() - ttl_hours * 3600
        deleted = 0
        for coll in self.client.list_collections():
            created_at = coll.metadata.get("created_at") if coll.metadata else None
            if created_at is not None and created_at < cutoff:
                self.client.delete_collection(coll.name)
                deleted += 1
        if deleted:
            logger.info("Cleanup: removed %d expired session(s)", deleted)
        return deleted
