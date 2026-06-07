import logging, pickle, re
from pathlib import Path
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

def tokenize(text: str) -> list[str]:
    return re.findall(r'\w+', text.lower())

class BM25Store:
    def __init__(self):
        self.bm25 = None
        self.chunks: list[dict] = []

    def add(self, chunks: list[dict]):
        self.chunks = chunks
        corpus = [tokenize(c["text"]) for c in chunks]
        self.bm25 = BM25Okapi(corpus)
        logger.info("BM25 index built | %d docs", len(chunks))

    def search(self, query: str, k=20) -> list[tuple[dict, float]]:
        tokens = tokenize(query)
        scores = self.bm25.get_scores(tokens)
        top_k = sorted(enumerate(scores), key=lambda x: -x[1])[:k]
        return [(self.chunks[i], float(s)) for i, s in top_k if s > 0]

    def save(self, path: str):
        p = Path(path); p.mkdir(parents=True, exist_ok=True)
        with open(p/"bm25.pkl","wb") as f:
            pickle.dump({"bm25": self.bm25, "chunks": self.chunks}, f)

    def load(self, path: str):
        with open(Path(path)/"bm25.pkl","rb") as f:
            data = pickle.load(f)
        self.bm25, self.chunks = data["bm25"], data["chunks"]