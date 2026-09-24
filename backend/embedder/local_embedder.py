import logging
from typing import List

from sentence_transformers import SentenceTransformer

from .base import BaseEmbedder

logger = logging.getLogger(__name__)


class LocalEmbedder(BaseEmbedder):
    """Free, no-API-key embedder. Runs the model on the machine itself."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        logger.info("Loading local embedding model: %s", model_name)
        # Forced to CPU: sentence-transformers otherwise auto-selects any
        # CUDA device it finds, and crashes at inference time if the
        # installed torch build doesn't support that GPU's compute
        # capability (seen on a GTX 1050 Ti here). CPU is also what the
        # deployment target (Render free tier) actually runs on, so this
        # isn't a downgrade in production.
        self.model = SentenceTransformer(model_name, device="cpu")
        self._model_name = model_name
        logger.info("Embedder ready | model=%s | dim=%d", model_name, self.dimension)

    def embed_text(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("embed_text() received empty input.")
        return self.model.encode(text, convert_to_numpy=True).tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            raise ValueError("embed_batch() received empty list.")
        return self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False).tolist()

    @property
    def dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()
