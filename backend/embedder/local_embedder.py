import logging
from typing import List
from sentence_transformers import SentenceTransformer
from .base import BaseEmbedder

logger = logging.getLogger(__name__)

class LocalEmbedder(BaseEmbedder):

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        logger.info("Loading model: %s", model_name)
        self.model = SentenceTransformer(model_name)
        self._model_name = model_name
        logger.info("Model ready | dim=%d", self.dimension)

    def embed_text(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("embed_text() received empty input.")
        return self.model.encode(text, convert_to_numpy=True).tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            raise ValueError("embed_batch() received empty list.")
        return self.model.encode(texts, convert_to_numpy=True).tolist()

    @property
    def dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()