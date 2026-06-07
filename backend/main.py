from logger import setup_logging
setup_logging()  

import logging
from embedder import get_embedder
import numpy as np

logger = logging.getLogger(__name__)


def cosine(a: list, b: list) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def main():
    emb = get_embedder()
    logger.info("Embedder ready | dimension=%d", emb.dimension)

    pairs = [
        ("The cat sat on the mat",   "A kitten rested on the rug",     "HIGH"),
        ("Stock markets fell today", "Investors saw major losses",      "HIGH"),
        ("The cat sat on the mat",   "Stock markets fell today",        "LOW"),
    ]

    print(f"\n{'Text A':<36} {'Text B':<36} {'Expect':<8} Score")
    print("-" * 92)
    for a, b, expected in pairs:
        score = cosine(emb.embed_text(a), emb.embed_text(b))
        print(f"{a:<36} {b:<36} {expected:<8} {score:.4f}")


if __name__ == "__main__":
    main()