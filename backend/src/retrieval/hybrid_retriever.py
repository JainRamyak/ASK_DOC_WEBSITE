import logging
from config import settings

logger = logging.getLogger(__name__)

def rrf_score(rank: int, k=60) -> float:
    return 1.0 / (k + rank + 1)

def hybrid_search(query: str, query_vec: list[float],
                  vector_store, bm25_store,
                  top_k=None) -> list[dict]:
    top_k = top_k or settings.top_k * 4  # retrieve more, rerank down

    vec_results = vector_store.search(query_vec, k=top_k)
    bm25_results = bm25_store.search(query, k=top_k)

    scores = {}
    for rank, (chunk, _) in enumerate(vec_results):
        key = (chunk["source"], chunk["chunk_index"])
        scores[key] = scores.get(key, {"chunk": chunk, "score": 0.0})
        scores[key]["score"] += rrf_score(rank)

    for rank, (chunk, _) in enumerate(bm25_results):
        key = (chunk["source"], chunk["chunk_index"])
        if key not in scores:
            scores[key] = {"chunk": chunk, "score": 0.0}
        scores[key]["score"] += rrf_score(rank)

    sorted_results = sorted(scores.values(),
                            key=lambda x: -x["score"])
    logger.info("Hybrid search: vec=%d bm25=%d merged=%d",
                len(vec_results), len(bm25_results), len(sorted_results))
    return [r["chunk"] for r in sorted_results[:top_k]]