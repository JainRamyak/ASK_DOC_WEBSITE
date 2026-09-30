"""
src/generation/answer_chain.py

Generates a cited answer from retrieved document chunks using an LLM.
The LLM client is created lazily (inside each function, not at import
time) so importing this module never crashes even if no API key is set.

Supported providers (set LLM_PROVIDER in .env):
    gemini    — Google Gemini 2.5 Flash   (free, no credit card)
    mistral   — Mistral Small Latest      (free tier)
    openai    — OpenAI GPT-4o-mini        (paid)
    anthropic — Anthropic Claude Sonnet   (paid)
"""
import logging
import re
from typing import List, Optional

from config import settings

logger = logging.getLogger(__name__)


class LLMConfigError(Exception):
    """Raised for any LLM provider misconfiguration (missing/invalid API
    key, missing SDK, unrecognized LLM_PROVIDER). Caught by /query in
    api/main.py and mapped to a 503 — never shown to the client
    verbatim."""


class LLMRateLimitError(Exception):
    """The provider rejected the answer call with HTTP 429. Raised by
    answer(); caught by /query in api/main.py and mapped to a 429 with a
    fixed message — never shown to the client verbatim."""


class LLMOverloadedError(Exception):
    """The provider rejected the answer call with HTTP 503 or 529
    (overloaded). Raised by answer(); caught by /query in api/main.py and
    mapped to a 503 with a fixed message — never shown verbatim."""


NOT_FOUND_MESSAGE = "I could not find this in the provided documents."

SYSTEM_PROMPT = f"""You are a precise document assistant.
Answer ONLY using the provided context.
For every factual claim, cite the source number in brackets like [1] or [2].
If the answer is not in the context, say exactly:
'{NOT_FOUND_MESSAGE}'
Do not use any outside knowledge, even if you know the answer independently."""


def _build_context(chunks: List[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source", "unknown")
        text = chunk.get("text", "")
        parts.append(f"[{i}] (source: {source})\n{text}")
    return "\n\n".join(parts)


_PDF_SOURCE_RE = re.compile(r"^.+#page(\d+)$")


def _pdf_page(chunk: dict) -> Optional[int]:
    """The PDF page number for a chunk, or None if it isn't a PDF page.
    The loader stamps PDF sources as "<file>#page<N>" with page=N, but the
    chunker defaults `page` to 1 for every other source type, so the page
    value alone can't identify a PDF. A URL that happens to end in
    "#pageN" must not count either, so URLs are excluded and the suffix
    must agree with the stored page."""
    source = chunk.get("source")
    page = chunk.get("page")
    if not isinstance(source, str) or not isinstance(page, int):
        return None
    if source.startswith(("http://", "https://")):
        return None
    m = _PDF_SOURCE_RE.match(source)
    if m and int(m.group(1)) == page:
        return page
    return None


def _sources(chunks: List[dict]) -> List[dict]:
    """One entry per context chunk, numbered with the same 1-based
    position _build_context labels it with, so an `[n]` marker in the
    answer identifies exactly one entry. `page` is present only for PDF
    pages."""
    sources = []
    for n, c in enumerate(chunks, 1):
        entry = {"n": n, "source": c.get("source"), "score": c.get("score", 0)}
        page = _pdf_page(c)
        if page is not None:
            entry["page"] = page
        sources.append(entry)
    return sources


def answer(question: str, chunks: List[dict]) -> dict:
    """
    Generate a cited answer from retrieved chunks.
    Returns: {"answer": str, "sources": [{"n": ..., "source": ..., "score": ...[, "page": ...]}]}
    """
    if not chunks:
        return {"answer": NOT_FOUND_MESSAGE, "sources": []}

    context = _build_context(chunks)
    provider = settings.llm_provider

    dispatch = {
        "gemini": _answer_gemini,
        "mistral": _answer_mistral,
        "openai": _answer_openai,
        "anthropic": _answer_anthropic,
    }

    if provider not in dispatch:
        raise LLMConfigError(
            f"Unknown LLM_PROVIDER='{provider}' in .env. Valid: {list(dispatch)}"
        )

    try:
        return dispatch[provider](question, context, chunks)
    except LLMConfigError:
        raise
    except Exception as e:
        status = _provider_status(e)
        if status == 429:
            raise LLMRateLimitError(f"{provider} rate limited (429)") from e
        if status in (503, 529):
            raise LLMOverloadedError(f"{provider} overloaded ({status})") from e
        raise


def _provider_status(e: Exception) -> Optional[int]:
    """HTTP status carried by a provider SDK exception, or None. Duck-typed
    so no SDK has to be imported: mistral/openai/anthropic expose
    `status_code`, google-genai exposes `code`. Only a real int counts
    (bool is an int subclass, so it is excluded explicitly)."""
    for attr in ("status_code", "code"):
        value = getattr(e, attr, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def check_llm_config() -> None:
    """Validates the configured LLM_PROVIDER is usable — the same checks
    _answer_<provider>() performs lazily on first real use — without
    constructing a client or making a network call. Raises
    LLMConfigError on failure. Used by GET /ready (api/main.py) so a
    misconfiguration is discoverable before a user hits /query."""
    provider = settings.llm_provider

    requires = {
        "gemini": _require_gemini,
        "mistral": _require_mistral,
        "openai": _require_openai,
        "anthropic": _require_anthropic,
    }

    if provider not in requires:
        raise LLMConfigError(
            f"Unknown LLM_PROVIDER='{provider}' in .env. Valid: {list(requires)}"
        )

    requires[provider]()


def _require_gemini() -> None:
    try:
        from google import genai  # noqa: F401
        from google.genai import types  # noqa: F401
    except ImportError:
        raise LLMConfigError("Run: pip install google-genai")

    if not settings.gemini_api_key:
        raise LLMConfigError(
            "GEMINI_API_KEY is not set in .env. Get a free key at https://aistudio.google.com"
        )


def _require_mistral() -> None:
    try:
        from mistralai.client import Mistral  # noqa: F401
    except ImportError:
        raise LLMConfigError("Run: pip install mistralai")

    if not settings.mistral_api_key:
        raise LLMConfigError(
            "MISTRAL_API_KEY is not set in .env. Get a free key at https://console.mistral.ai"
        )


def _require_openai() -> None:
    try:
        from openai import OpenAI  # noqa: F401
    except ImportError:
        raise LLMConfigError("Run: pip install openai")

    if not settings.openai_api_key:
        raise LLMConfigError("OPENAI_API_KEY is not set in .env")


def _require_anthropic() -> None:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        raise LLMConfigError("Run: pip install anthropic")

    if not settings.anthropic_api_key:
        raise LLMConfigError(
            "ANTHROPIC_API_KEY is not set in .env. Get a key at https://console.anthropic.com"
        )


def _answer_gemini(question: str, context: str, chunks: List[dict]) -> dict:
    _require_gemini()
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=f"Context:\n{context}\n\nQuestion: {question}",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=settings.gemini_max_output_tokens,
            # gemini-2.5+/3.x models "think" before answering, and that
            # thinking is billed against max_output_tokens by default —
            # with no cap here the model can burn the whole budget on
            # invisible reasoning and leave nothing for the visible
            # answer, which comes back truncated mid-sentence. This is a
            # plain grounded-QA task with no need for deliberation, so
            # thinking is switched off entirely.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    answer_text = response.text or NOT_FOUND_MESSAGE
    logger.info("Answer generated | provider=gemini | chars=%d", len(answer_text))
    return {"answer": answer_text, "sources": _sources(chunks)}


def _answer_mistral(question: str, context: str, chunks: List[dict]) -> dict:
    _require_mistral()
    from mistralai.client import Mistral

    client = Mistral(api_key=settings.mistral_api_key)
    response = client.chat.complete(
        model=settings.mistral_model,
        max_tokens=settings.mistral_max_tokens,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ],
    )
    choices = response.choices or []
    answer_text = (choices[0].message.content if choices else None) or NOT_FOUND_MESSAGE
    logger.info("Answer generated | provider=mistral | chars=%d", len(answer_text))
    return {"answer": answer_text, "sources": _sources(chunks)}


def _answer_openai(question: str, context: str, chunks: List[dict]) -> dict:
    _require_openai()
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=settings.openai_model,
        max_tokens=settings.openai_max_tokens,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ],
    )
    choices = resp.choices or []
    answer_text = (choices[0].message.content if choices else None) or NOT_FOUND_MESSAGE
    logger.info("Answer generated | provider=openai | chars=%d", len(answer_text))
    return {"answer": answer_text, "sources": _sources(chunks)}


def _answer_anthropic(question: str, context: str, chunks: List[dict]) -> dict:
    _require_anthropic()
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    # Model IDs change over time — if this 404s, check
    # https://docs.claude.com/en/docs/about-claude/models for the current list.
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=settings.anthropic_max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}],
    )
    # message.content is a list of content blocks; a stop_reason like
    # "refusal" or a non-text block (e.g. a tool_use block) can leave it
    # empty of TextBlocks or empty outright — index [0] blindly risks an
    # IndexError/AttributeError instead of a graceful not-found answer.
    answer_text = next(
        (b.text for b in message.content if hasattr(b, "text")), None
    ) or NOT_FOUND_MESSAGE
    logger.info("Answer generated | provider=anthropic | chars=%d", len(answer_text))
    return {"answer": answer_text, "sources": _sources(chunks)}


# --------------------------------------------------------------------------
# Query rewriting for conversational follow-ups. Opt-in via
# ENABLE_QUERY_REWRITING=true — resolves "how does it work?" into a
# standalone question using recent chat history, before it ever reaches
# retrieval. Separate, minimal provider dispatch rather than reusing the
# _answer_*() functions above: those are coupled to the grounded-answer
# format (context + citation prompt); duplicating a few lines here is
# lower-risk than reshaping already-tested code to serve two prompt shapes.
# --------------------------------------------------------------------------

REWRITE_SYSTEM_PROMPT = """Rewrite the user's latest question into a
standalone question that doesn't depend on the conversation history to
be understood. Use the history only to resolve references like "it",
"that", "the second one", etc. If the question is already standalone,
return it unchanged. Reply with ONLY the rewritten question, nothing else."""


def rewrite_query(question: str, history: List[str]) -> str:
    """`history` is a list of the user's previous questions in this
    session, most recent last. Falls back to the original question,
    logged but not raised, on any failure — a broken rewrite should
    degrade to normal retrieval, not break the whole request."""
    if not history:
        return question

    history_text = "\n".join(f"- {h}" for h in history[-5:])
    user_prompt = f"Conversation history:\n{history_text}\n\nLatest question: {question}"

    try:
        rewritten = _call_llm_plain(REWRITE_SYSTEM_PROMPT, user_prompt).strip()
        if rewritten:
            logger.info("Query rewritten: %r -> %r", question, rewritten)
            return rewritten
    except Exception as e:
        logger.warning("Query rewrite failed, using original question: %s", e)
    return question


def _call_llm_plain(system_prompt: str, user_prompt: str) -> str:
    provider = settings.llm_provider

    if provider == "gemini":
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        resp = client.models.generate_content(
            model=settings.gemini_model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=300,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        return resp.text or ""

    if provider == "mistral":
        from mistralai.client import Mistral

        client = Mistral(api_key=settings.mistral_api_key)
        resp = client.chat.complete(
            model=settings.mistral_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        choices = resp.choices or []
        return (choices[0].message.content if choices else None) or ""

    if provider == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        choices = resp.choices or []
        return (choices[0].message.content if choices else None) or ""

    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=200,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return next((b.text for b in message.content if hasattr(b, "text")), None) or ""

    raise ValueError(f"Unknown LLM_PROVIDER='{provider}'")
