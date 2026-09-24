"""
config.py — single source of truth for all configuration.

Usage anywhere in the project:
    from config import settings
    print(settings.embedder_type)
    print(settings.llm_provider)
"""
import os

from dotenv import load_dotenv

load_dotenv(override=True)


def _optional(key: str, default: str = "") -> str:
    """Read an env var, return default if missing or empty."""
    return os.getenv(key, default).strip()


class _Settings:
    # Embedder selection
    embedder_type: str = _optional("EMBEDDER_TYPE", "local").lower()
    local_model_name: str = _optional("LOCAL_MODEL_NAME", "all-MiniLM-L6-v2")

    # Embedding API keys
    openai_api_key: str = _optional("OPENAI_API_KEY")
    gemini_api_key: str = _optional("GEMINI_API_KEY")

    # LLM for answer generation. Options: gemini | mistral | openai | anthropic
    llm_provider: str = _optional("LLM_PROVIDER", "gemini").lower()
    anthropic_api_key: str = _optional("ANTHROPIC_API_KEY")
    mistral_api_key: str = _optional("MISTRAL_API_KEY")

    gemini_model: str = _optional("GEMINI_MODEL", "gemini-3.6-flash")
    mistral_model: str = _optional("MISTRAL_MODEL", "mistral-small-latest")
    openai_model: str = _optional("OPENAI_MODEL", "gpt-4o-mini")
    anthropic_model: str = _optional("ANTHROPIC_MODEL", "claude-sonnet-5")

    # Per-provider answer length cap, same pattern as the model names
    # above. Providers price and cap output tokens differently, and a
    # single hardcoded number in answer_chain.py silently breaks the
    # moment a provider or model is swapped (Anthropic's 1024 vs.
    # Gemini's 2048 gave inconsistent, sometimes-truncated answers
    # depending on which LLM_PROVIDER was active). Each provider gets
    # its own env var so switching providers, or a future 5th provider,
    # never requires touching this file again.
    gemini_max_output_tokens: int = int(_optional("GEMINI_MAX_OUTPUT_TOKENS", "2048"))
    mistral_max_tokens: int = int(_optional("MISTRAL_MAX_TOKENS", "2048"))
    openai_max_tokens: int = int(_optional("OPENAI_MAX_TOKENS", "2048"))
    anthropic_max_tokens: int = int(_optional("ANTHROPIC_MAX_TOKENS", "2048"))

    # Chunking
    chunk_size: int = int(_optional("CHUNK_SIZE", "512"))
    chunk_overlap: int = int(_optional("CHUNK_OVERLAP", "50"))

    # Retrieval
    top_k: int = int(_optional("TOP_K_RETRIEVAL", "5"))

    # Query input bound — mirrors the file-size cap: a public API
    # boundary shouldn't accept an unbounded string to embed/rerank.
    max_question_length: int = int(_optional("MAX_QUESTION_LENGTH", "2000"))

    # --- Grounding gate ---------------------------------------------------
    # After reranking, the top chunk's cross-encoder score must be >= this
    # value or the pipeline returns "not found in document" WITHOUT calling
    # the LLM at all. cross-encoder/ms-marco-MiniLM-L-6-v2 outputs raw
    # (unbounded) logits, not probabilities: strongly relevant pairs score
    # roughly > 0, unrelated pairs commonly score < -5. This default is a
    # starting point, not a guarantee — calibrate it against your own
    # documents using scripts/calibrate_threshold.py before relying on it.
    relevance_threshold: float = float(_optional("RELEVANCE_THRESHOLD", "-3.0"))

    # File upload limits
    max_file_size_mb: int = int(_optional("MAX_FILE_SIZE_MB", "20"))
    max_files_per_upload: int = int(_optional("MAX_FILES_PER_UPLOAD", "10"))

    # Session storage
    chroma_persist_dir: str = _optional("CHROMA_PERSIST_DIR", "outputs/chroma")
    session_ttl_hours: int = int(_optional("SESSION_TTL_HOURS", "24"))

    # CORS
    allowed_origins_raw: str = _optional("ALLOWED_ORIGINS", "")

    # Rate limiting (see src/utils/rate_limit.py — single-process only)
    rate_limit_requests: int = int(_optional("RATE_LIMIT_REQUESTS", "20"))
    rate_limit_window_seconds: int = int(_optional("RATE_LIMIT_WINDOW_SECONDS", "60"))

    # URL ingestion domain allowlist. Empty = any public URL allowed
    # (still subject to the SSRF guard in web_loader.py either way).
    # Comma-separated, e.g. "wikipedia.org,docs.python.org"
    url_allowed_domains_raw: str = _optional("URL_ALLOWED_DOMAINS", "")

    # Conversational query rewriting — resolves follow-up questions
    # ("how does it work?") against recent chat history before retrieval.
    # Costs one extra (small, fast) LLM call per question when enabled.
    enable_query_rewriting: bool = _optional("ENABLE_QUERY_REWRITING", "false").lower() == "true"

    # OCR fallback for scanned PDF pages with no text layer. Requires
    # the tesseract system package (see requirements.txt comment) — the
    # Dockerfile installs it unconditionally, so this is a pure toggle
    # in a Docker deployment. Off by default (slow, extra dependency).
    enable_ocr: bool = _optional("ENABLE_OCR", "false").lower() == "true"

    # Logging
    log_level: str = _optional("LOG_LEVEL", "INFO").upper()

    @property
    def allowed_origins(self) -> list[str]:
        if not self.allowed_origins_raw.strip():
            return ["*"]
        return [o.strip() for o in self.allowed_origins_raw.split(",") if o.strip()]

    @property
    def url_allowed_domains(self) -> list[str]:
        if not self.url_allowed_domains_raw.strip():
            return []
        return [d.strip().lower() for d in self.url_allowed_domains_raw.split(",") if d.strip()]

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
