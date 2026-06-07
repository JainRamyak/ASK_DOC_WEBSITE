import logging
from embedder import get_embedder
from src.ingestion.loader import load_documents
from src.ingestion.chunker import chunk_documents
from src.storage.chroma_store import ChromaStore
from src.retrieval.reranker import Reranker
from src.generation.answer_chain import answer
from config import settings

logger = logging.getLogger(__name__)

STORE_PATH = "outputs/store"

class AskMyDocsPipeline:
    def __init__(self):
        self.embedder   = get_embedder()
        self.chroma_store = ChromaStore()
        self.reranker = Reranker()
        

    def ingest(self, directory: str, session_id: str = "default") -> str:
        docs   = load_documents(directory)
        chunks = chunk_documents(docs)
        vecs = self.embedder.embed_batch([c["text"] for c in chunks])

        self.chroma_store.add(
            session_id=session_id,
            chunks=[c["text"] for c in chunks],
            embeddings=vecs,
            metadatas=chunks
        )
        logger.info("Ingested %d chunks from %s", len(chunks), directory)
        return len(chunks)

    def ask(self, question: str, session_id: str = "default") -> dict:
        if not question or not question.strip():
            return {"answer": "No relevant documents found.", "sources": []}
        q_vec = self.embedder.embed_text(question)

        results = self.chroma_store.query(
            session_id=session_id,
            query_embedding=q_vec,
            top_k=settings.top_k * 4
        )

        documents = results["documents"][0]
        metadatas = results["metadatas"][0]

        candidates = []

        for doc, meta in zip(documents, metadatas):
            candidates.append({
                "text": doc,
                "source": meta.get("source", "unknown")
            })

        top_chunks = self.reranker.rerank(
            question,
            candidates,
            top_n=settings.top_k
        )

        return answer(question, top_chunks)