import logging
from embedder import get_embedder
from src.ingestion.loader import load_documents
from src.ingestion.chunker import chunk_documents
from src.storage.vector_store import FAISSVectorStore
from src.storage.bm25_store import BM25Store
from src.retrieval.hybrid_retriever import hybrid_search
from src.retrieval.reranker import Reranker
from src.generation.answer_chain import answer
from config import settings

logger = logging.getLogger(__name__)

STORE_PATH = "outputs/store"

class AskMyDocsPipeline:
    def __init__(self):
        self.embedder   = get_embedder()
        self.vec_store  = FAISSVectorStore(self.embedder.dimension)
        self.bm25_store = BM25Store()
        self.reranker   = Reranker()
        self.vec_store.load(STORE_PATH)
        self.bm25_store.load(STORE_PATH)

    def ingest(self, directory: str) -> int:
        docs   = load_documents(directory)
        chunks = chunk_documents(docs)
        vecs   = self.embedder.embed_batch([c["text"] for c in chunks])
        self.vec_store.add(chunks, vecs)
        self.bm25_store.add(chunks)
        self.vec_store.save(STORE_PATH)
        self.bm25_store.save(STORE_PATH)
        logger.info("Ingested %d chunks from %s", len(chunks), directory)
        return len(chunks)

    def ask(self, question: str) -> dict:
        if not question or not question.strip():
            return {"answer": "No relevant documents found.", "sources": []}
        q_vec      = self.embedder.embed_text(question)
        candidates = hybrid_search(question, q_vec,
                                   self.vec_store, self.bm25_store,
                                   top_k=settings.top_k * 4)
        top_chunks = self.reranker.rerank(question, candidates,
                                          top_n=settings.top_k)
        return answer(question, top_chunks)