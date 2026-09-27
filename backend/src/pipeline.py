import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

from config import settings
from embedder import get_embedder
from src.generation.answer_chain import NOT_FOUND_MESSAGE, answer, rewrite_query
from src.ingestion.chunker import chunk_documents
from src.ingestion.loader import load_documents
from src.ingestion.web_loader import load_url
from src.retrieval.reranker import Reranker
from src.storage.chroma_store import ChromaStore

logger = logging.getLogger(__name__)


def _hash_file(path: Path) -> str:
    """SHA-256 hex digest of a file's raw bytes (G27 dedup identity)."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class IngestResult:
    """Outcome of ingesting a directory. `indexed`, `skipped`, and
    `already_indexed` are keyed by on-disk filename (or, for `ingest_url`,
    by the URL string). `skipped` maps to a loader reason code;
    `already_indexed` maps to the content hash that was already present
    in the session (G27 — the file/URL was not re-ingested)."""
    chunks: int
    indexed: set = field(default_factory=set)
    skipped: dict = field(default_factory=dict)
    already_indexed: dict = field(default_factory=dict)


class AskMyDocsPipeline:
    def __init__(self):
        self.embedder = get_embedder()
        self.chroma_store = ChromaStore(persist_dir=settings.chroma_persist_dir)
        self.reranker = Reranker()

    def ingest(self, directory: str, session_id: str = "default") -> int:
        """Load, chunk, embed, and store every supported file found in
        `directory`. Returns the number of chunks ingested. Safe to call
        multiple times with the same session_id to add more documents to
        an existing session."""
        return self.ingest_with_report(directory, session_id=session_id).chunks

    def ingest_with_report(self, directory: str, session_id: str = "default") -> IngestResult:
        """Same as `ingest()`, but also says which files contributed text,
        which were skipped (and why), and which were already indexed in
        this session (G27 — identical content is not stored twice)."""
        docs = load_documents(directory)
        skipped = dict(getattr(docs, "skipped", {}))
        if not docs:
            logger.warning("No supported documents found in %s", directory)
            return IngestResult(chunks=0, skipped=skipped)

        all_files = {d["file"] for d in docs}
        file_hashes = {f: _hash_file(Path(directory) / f) for f in all_files}

        # Within-batch dedup: the first file (in doc order) to show a
        # given hash is this request's "winner" for that hash and is the
        # only one that reaches the store; a later file in the same
        # request sharing that hash — same content, whatever its name —
        # never gets embedded/stored and is reported already-indexed
        # without needing a database round trip to know it.
        winner_by_hash: dict = {}
        duplicate_within_batch: set = set()
        for d in docs:
            f = d["file"]
            h = file_hashes[f]
            winner_by_hash.setdefault(h, f)
            if winner_by_hash[h] != f:
                duplicate_within_batch.add(f)

        docs_to_store = [d for d in docs if d["file"] not in duplicate_within_batch]
        for d in docs_to_store:
            d["content_hash"] = file_hashes[d["file"]]

        count, added_hashes = self._store_docs(docs_to_store, session_id)
        logger.info("Ingested %d chunk(s) from %s | session=%s",
                    count, directory, session_id)

        indexed = {
            f for f in all_files
            if f not in duplicate_within_batch and file_hashes[f] in added_hashes
        } if count else set()
        already_indexed = {
            f: file_hashes[f]
            for f in all_files
            if f in duplicate_within_batch or file_hashes[f] not in added_hashes
        }

        return IngestResult(
            chunks=count,
            indexed=indexed,
            skipped=skipped,
            already_indexed=already_indexed,
        )

    def ingest_url(self, url: str, session_id: str = "default") -> IngestResult:
        """Fetch a live URL, chunk, embed, and store it — same shape and
        same session semantics as `ingest_with_report()`, just a
        different source. A URL whose extracted text hash is already
        indexed in this session contributes 0 new chunks and is reported
        via `IngestResult.already_indexed` (G27)."""
        docs = load_url(url)
        if not docs:
            logger.warning("No extractable text found at %s", url)
            return IngestResult(chunks=0)

        content_hash = hashlib.sha256(docs[0]["text"].encode("utf-8")).hexdigest()
        for d in docs:
            d["content_hash"] = content_hash

        count, added_hashes = self._store_docs(docs, session_id)
        if content_hash in added_hashes:
            logger.info("Ingested %d chunk(s) from %s | session=%s", count, url, session_id)
            return IngestResult(chunks=count, indexed={url})

        logger.info("URL already indexed, skipped | %s | session=%s", url, session_id)
        return IngestResult(chunks=0, already_indexed={url: content_hash})

    def _store_docs(self, docs: list[dict], session_id: str) -> tuple[int, set]:
        """Chunks, embeds, and stores `docs`. Returns (chunks actually
        added, set of content_hash values newly added) — a chunk whose
        hash was already present in the session is embedded but not
        stored (see ChromaStore.add), so `count` can be less than the
        total number of chunks computed from `docs`."""
        chunks = chunk_documents(docs)
        if not chunks:
            return 0, set()

        vecs = self.embedder.embed_batch([c["text"] for c in chunks])
        added_hashes = self.chroma_store.add(
            session_id=session_id,
            chunks=[c["text"] for c in chunks],
            embeddings=vecs,
            metadatas=chunks,
        )
        added_count = sum(
            1 for c in chunks
            if c.get("content_hash") is None or c.get("content_hash") in added_hashes
        )
        return added_count, added_hashes

    def retrieve_and_rerank(self, question: str, session_id: str, top_n: int) -> list[dict]:
        """Embed the question, pull top_k*4 candidates from the session's
        collection, and rerank down to `top_n`. Shared by `ask()` and
        `scripts/calibrate_threshold.py` so calibration always scores
        against exactly what production retrieval computes."""
        q_vec = self.embedder.embed_text(question)
        results = self.chroma_store.query(
            session_id=session_id,
            query_embedding=q_vec,
            top_k=settings.top_k * 4,
        )

        documents = results["documents"][0]
        metadatas = results["metadatas"][0]

        if not documents:
            return []

        candidates = [
            {"text": doc, "source": meta.get("source", "unknown")}
            for doc, meta in zip(documents, metadatas)
        ]

        return self.reranker.rerank(question, candidates, top_n=top_n)

    def ask(self, question: str, session_id: str = "default", history: list[str] | None = None) -> dict:
        """Retrieve, rerank, and answer. Returns:
        {"answer": str, "sources": list[dict], "grounded": bool}

        `grounded=False` means the question was rejected before the LLM
        was even called, because nothing in the document was relevant
        enough — see config.settings.relevance_threshold.

        `history` (optional): previous user questions in this session,
        most recent last. Only used if ENABLE_QUERY_REWRITING=true — see
        src/generation/answer_chain.rewrite_query(). Ignored otherwise,
        so passing it costs nothing when the feature is off.
        """
        if not question or not question.strip():
            return {"answer": NOT_FOUND_MESSAGE, "sources": [], "grounded": False}

        if not self.chroma_store.session_exists(session_id):
            return {
                "answer": "No documents have been uploaded for this session yet.",
                "sources": [],
                "grounded": False,
                "reason": "no_session",
            }

        retrieval_question = question
        if settings.enable_query_rewriting and history:
            retrieval_question = rewrite_query(question, history)

        top_chunks = self.retrieve_and_rerank(retrieval_question, session_id, top_n=settings.top_k)

        # --- Hard grounding gate ---------------------------------------
        # This is what actually enforces "don't answer from outside
        # knowledge" — a code-level check, not just a prompt instruction
        # the LLM could ignore.
        if not top_chunks or top_chunks[0]["score"] < settings.relevance_threshold:
            logger.info(
                "Rejected as not grounded | top_score=%s | threshold=%s",
                top_chunks[0]["score"] if top_chunks else None,
                settings.relevance_threshold,
            )
            return {"answer": NOT_FOUND_MESSAGE, "sources": [], "grounded": False}

        # Answer generation uses the ORIGINAL question, not the rewritten
        # one — the rewrite is a retrieval aid, the user asked the
        # original phrasing and should see it addressed directly.
        result = answer(question, top_chunks)
        result["grounded"] = True
        return result
