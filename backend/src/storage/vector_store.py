"""
src/storage/vector_store.py
FAISS vector store with persistence (save/load).
"""
import logging
import pickle
from pathlib import Path

import faiss
import numpy as np

logger = logging.getLogger(__name__)


class FAISSVectorStore:
    def __init__(self, dimension: int):
        self.dim = dimension
        self.index = faiss.IndexFlatIP(dimension)
        self.chunks: list[dict] = []

    def add(self, chunks, vectors):
        arr = np.array(vectors, dtype="float32")
        faiss.normalize_L2(arr)
        self.index.add(arr)
        self.chunks.extend(chunks)

    def search(self, query_vec, k=5):
        if self.index.ntotal == 0:
            return []
        arr = np.array([query_vec], dtype="float32")
        faiss.normalize_L2(arr)
        scores, idxs = self.index.search(arr, min(k, self.index.ntotal))
        return [
            (self.chunks[i], float(s))
            for s, i in zip(scores[0], idxs[0])
            if i != -1
        ]

    def save(self, path: str = "outputs"):
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(p / "index.faiss"))
        with open(p / "chunks.pkl", "wb") as f:
            pickle.dump(self.chunks, f)
        logger.info("FAISS index saved to %s", path)

    def load(self, path: str = "outputs") -> bool:
        p = Path(path)
        index_file = p / "index.faiss"
        chunks_file = p / "chunks.pkl"
        if not index_file.exists() or not chunks_file.exists():
            return False
        self.index = faiss.read_index(str(index_file))
        with open(chunks_file, "rb") as f:
            self.chunks = pickle.load(f)
        logger.info("FAISS index loaded from %s (%d vectors)", path, self.index.ntotal)
        return True

    @property
    def size(self):
        return self.index.ntotal