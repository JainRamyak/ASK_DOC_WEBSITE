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
from typing import List

from config import settings

logger = logging.getLogger(__name__)

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


def _sources(chunks: List[dict]) -> List[dict]:
    """Dedupe by source URL/filename, keeping the highest score seen.
    Several of the top-N reranked chunks often come from the same page
    or file — without this, the UI shows the identical citation link
    repeated N times instead of once."""
    best: dict = {}
    order: List[str] = []
    for c in chunks:
        src = c.get("source")
        score = c.get("score", 0)
        if src not in best:
            best[src] = score
            order.append(src)
        elif score > best[src]:
            best[src] = score
    return [{"source": src, "score": best[src]} for src in order]


def answer(question: str, chunks: List[dict]) -> dict:
    """
    Generate a cited answer from retrieved chunks.
    Returns: {"answer": str, "sources": [{"source": ..., "score": ...}]}
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
        raise ValueError(
            f"Unknown LLM_PROVIDER='{provider}' in .env. Valid: {list(dispatch)}"
        )

    return dispatch[provider](question, context, chunks)


def _answer_gemini(question: str, context: str, chunks: List[dict]) -> dict:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise ImportError("Run: pip install google-genai")

    if not settings.gemini_api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set in .env. Get a free key at https://aistudio.google.com"
        )

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
    try:
        from mistralai.client import Mistral
    except ImportError:
        raise ImportError("Run: pip install mistralai")

    if not settings.mistral_api_key:
        raise EnvironmentError(
            "MISTRAL_API_KEY is not set in .env. Get a free key at https://console.mistral.ai"
        )

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
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Run: pip install openai")

    if not settings.openai_api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set in .env")

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
    try:
        import anthropic
    except ImportError:
        raise ImportError("Run: pip install anthropic")

    if not settings.anthropic_api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set in .env. Get a key at https://console.anthropic.com"
        )

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
