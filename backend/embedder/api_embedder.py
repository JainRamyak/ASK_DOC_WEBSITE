import logging
from typing import List

from config import settings

from .base import BaseEmbedder

logger = logging.getLogger(__name__)


class APIEmbedder(BaseEmbedder):
    """Cloud embedder. Only used if EMBEDDER_TYPE=openai or EMBEDDER_TYPE=gemini."""

    PROVIDER_CONFIG = {
        "openai": {
            "model": "text-embedding-3-small",
            "dimension": 1536,
            "batch_limit": 2048,
        },
        "gemini": {
            "model": "models/text-embedding-004",
            "dimension": 768,
            "batch_limit": 100,
        },
    }

    def __init__(self, provider: str = "openai"):
        if provider not in self.PROVIDER_CONFIG:
            raise ValueError(
                f"Unknown provider '{provider}'. Valid: {list(self.PROVIDER_CONFIG)}"
            )
        self.provider = provider
        self.config = self.PROVIDER_CONFIG[provider]
        settings.validate_provider(provider)
        self._init_client()

    def _init_client(self):
        if self.provider == "openai":
            from openai import OpenAI

            self.client = OpenAI(api_key=settings.openai_api_key)
        elif self.provider == "gemini":
            from google import genai

            self.client = genai.Client(api_key=settings.gemini_api_key)

    def embed_text(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("embed_text() received empty input.")
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            raise ValueError("embed_batch() received empty list.")
        limit = self.config["batch_limit"]
        all_vecs: List[List[float]] = []
        for i in range(0, len(texts), limit):
            all_vecs.extend(self._call_api(texts[i:i + limit]))
        return all_vecs

    def _call_api(self, texts: List[str]) -> List[List[float]]:
        if self.provider == "openai":
            resp = self.client.embeddings.create(input=texts, model=self.config["model"])
            return [x.embedding for x in sorted(resp.data, key=lambda x: x.index)]
        if self.provider == "gemini":
            resp = self.client.models.embed_content(model=self.config["model"], contents=texts)
            return [e.values for e in resp.embeddings]
        raise ValueError(f"Unhandled provider {self.provider}")

    @property
    def dimension(self) -> int:
        return self.config["dimension"]
