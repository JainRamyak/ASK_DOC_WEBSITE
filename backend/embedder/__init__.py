import logging
from .base import BaseEmbedder
from .local_embedder import LocalEmbedder
from .api_embedder import APIEmbedder
from config import settings   

logger = logging.getLogger(__name__)

def get_embedder() -> BaseEmbedder:
    etype = settings.embedder_type
    logger.info("Initialising embedder | type=%s", etype)
    if etype == "local":
        return LocalEmbedder(model_name=settings.local_model_name)
    elif etype in ("openai", "gemini"):
        return APIEmbedder(provider=etype)
    else:
        raise ValueError(f"Unknown EMBEDDER_TYPE='{etype}'")

__all__ = ["get_embedder","BaseEmbedder","LocalEmbedder","APIEmbedder"]