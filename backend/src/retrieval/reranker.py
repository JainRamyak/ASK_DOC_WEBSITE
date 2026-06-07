import logging
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

class Reranker:
    def __init__(self, model="cross-encoder/ms-marco-MiniLM-L-6-v2"):
        logger.info("Loading reranker: %s", model)
        self.model = CrossEncoder(model)

    def rerank(self, query: str, chunks: list[dict],
               top_n=5) -> list[dict]:
        pairs = [(query, c["text"]) for c in chunks]
        scores = self.model.predict(pairs)
        ranked = sorted(zip(chunks, scores),
                        key=lambda x: -x[1])
        top = [c for c, _ in ranked[:top_n]]
        logger.info("Reranked %d -> %d chunks", len(chunks), len(top))
        return top