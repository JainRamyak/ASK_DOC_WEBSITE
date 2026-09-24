import logging

from config import settings

from .api_embedder import APIEmbedder
from .base import BaseEmbedder
from .local_embedder import LocalEmbedder

logger = logging.getLogger(__name__)


def get_embedder() -> BaseEmbedder:
    etype = settings.embedder_type
    logger.info("Initialising embedder | type=%s", etype)

    if etype == "local":
        return LocalEmbedder(model_name=settings.local_model_name)
    if etype in ("openai", "gemini"):
        return APIEmbedder(provider=etype)

    raise ValueError(f"Unknown EMBEDDER_TYPE='{etype}'. Valid: local, openai, gemini")


__all__ = ["get_embedder", "BaseEmbedder", "LocalEmbedder", "APIEmbedder"]
