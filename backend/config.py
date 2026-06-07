"""
config.py — single source of truth for all configuration.

Usage anywhere in the project:
    from config import settings
    print(settings.embedder_type)
    print(settings.llm_provider)
    print(settings.gemini_api_key)
"""
import os
from dotenv import load_dotenv

load_dotenv(override=True)


# --- helper functions (must be defined BEFORE _Settings class) ---

def _optional(key: str, default: str = "") -> str:
    """Read an env var, return default if missing or empty."""
    return os.getenv(key, default).strip()


# --- settings class ---

class _Settings:
    # Embedder selection
    embedder_type: str      = _optional("EMBEDDER_TYPE", "local").lower()
    local_model_name: str   = _optional("LOCAL_MODEL_NAME", "all-MiniLM-L6-v2")

    # Embedding API keys
    openai_api_key: str     = _optional("OPENAI_API_KEY")
    gemini_api_key: str     = _optional("GEMINI_API_KEY")

    # LLM for answer generation
    # Options: gemini | mistral | openai | anthropic
    llm_provider: str       = _optional("LLM_PROVIDER", "gemini")
    anthropic_api_key: str  = _optional("ANTHROPIC_API_KEY")
    mistral_api_key: str    = _optional("MISTRAL_API_KEY")

    # Chunking
    chunk_size: int         = int(_optional("CHUNK_SIZE", "512"))
    chunk_overlap: int      = int(_optional("CHUNK_OVERLAP", "50"))

    # Retrieval
    top_k: int              = int(_optional("TOP_K_RETRIEVAL", "5"))

    # Logging
    log_level: str          = _optional("LOG_LEVEL", "INFO").upper()

    def validate_provider(self, provider: str) -> None:
        """Call this before activating an embedding API provider."""
        if provider == "openai" and not self.openai_api_key:
            raise EnvironmentError(
                "EMBEDDER_TYPE=openai requires OPENAI_API_KEY in .env"
            )
        if provider == "gemini" and not self.gemini_api_key:
            raise EnvironmentError(
                "EMBEDDER_TYPE=gemini requires GEMINI_API_KEY in .env"
            )


# Singleton — import this everywhere, never instantiate _Settings directly
settings = _Settings()