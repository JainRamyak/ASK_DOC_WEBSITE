import logging

from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)


class Reranker:
    """Re-scores (question, chunk) pairs together — much more accurate
    than embedding-similarity alone for deciding what's actually relevant."""

    def __init__(self, model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        logger.info("Loading reranker: %s", model)
        # See embedder/local_embedder.py — forced to CPU for the same reason.
        self.model = CrossEncoder(model, device="cpu")

    def rerank(self, query: str, chunks: list[dict], top_n: int = 5) -> list[dict]:
        if not chunks:
            return []

        pairs = [(query, c["text"]) for c in chunks]
        scores = self.model.predict(pairs)

        ranked = sorted(zip(chunks, scores), key=lambda x: -x[1])
        top = [{**c, "score": float(score)} for c, score in ranked[:top_n]]

        logger.info("Reranked %d -> %d chunk(s) | top_score=%.3f",
                    len(chunks), len(top), top[0]["score"] if top else float("-inf"))
        return top
