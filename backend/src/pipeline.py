import logging

from config import settings
from embedder import get_embedder
from src.generation.answer_chain import NOT_FOUND_MESSAGE, answer, rewrite_query
from src.ingestion.chunker import chunk_documents
from src.ingestion.loader import load_documents
from src.ingestion.web_loader import load_url
from src.retrieval.reranker import Reranker
from src.storage.chroma_store import ChromaStore

logger = logging.getLogger(__name__)


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
        docs = load_documents(directory)
        if not docs:
            logger.warning("No supported documents found in %s", directory)
            return 0

        count = self._store_docs(docs, session_id)
        logger.info("Ingested %d chunk(s) from %s | session=%s",
                    count, directory, session_id)
        return count

    def ingest_url(self, url: str, session_id: str = "default") -> int:
        """Fetch a live URL, chunk, embed, and store it — same shape and
        same session semantics as `ingest()`, just a different source."""
        docs = load_url(url)
        if not docs:
            logger.warning("No extractable text found at %s", url)
            return 0

        count = self._store_docs(docs, session_id)
        logger.info("Ingested %d chunk(s) from %s | session=%s", count, url, session_id)
        return count

    def _store_docs(self, docs: list[dict], session_id: str) -> int:
        chunks = chunk_documents(docs)
        if not chunks:
            return 0

        vecs = self.embedder.embed_batch([c["text"] for c in chunks])
        self.chroma_store.add(
            session_id=session_id,
            chunks=[c["text"] for c in chunks],
            embeddings=vecs,
            metadatas=chunks,
        )
        return len(chunks)

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
