"""
src/generation/answer_chain.py

Generates a cited answer from retrieved document chunks using an LLM.
The LLM client is created lazily (inside the function, not at import time)
so importing this module never crashes even if the API key isn't set yet.

Supported providers (set LLM_PROVIDER in .env):
    gemini    — Google Gemini 2.5 Flash   (FREE, no credit card needed)
    mistral   — Mistral Small Latest      (FREE tier available)
    openai    — OpenAI GPT-4o-mini        (requires paid credits)
    anthropic — Anthropic Claude Sonnet   (requires paid credits)
"""
import logging
from typing import List
from config import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a precise document assistant.
Answer ONLY using the provided context.
For every factual claim, cite the source number in brackets like [1] or [2].
If the answer is not in the context, say exactly:
'I could not find this in the provided documents.'
Do not use any outside knowledge."""


def _build_context(chunks: List[dict]) -> str:
    """Format retrieved chunks into a numbered reference block."""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source", "unknown")
        text = chunk.get("text", "")
        parts.append(f"[{i}] (source: {source})\n{text}")
    return "\n\n".join(parts)


def answer(question: str, chunks: List[dict]) -> dict:
    """
    Generate a cited answer from retrieved chunks.

    Args:
        question: The user's question string.
        chunks:   List of dicts with keys 'text', 'source', 'score'.

    Returns:
        {"answer": str, "sources": list of {source, score}}
    """
    if not chunks:
        return {"answer": "No relevant documents found.", "sources": []}

    context = _build_context(chunks)
    provider = settings.llm_provider.lower()

    if provider == "gemini":
        return _answer_gemini(question, context, chunks)
    elif provider == "mistral":
        return _answer_mistral(question, context, chunks)
    elif provider == "openai":
        return _answer_openai(question, context, chunks)
    elif provider == "anthropic":
        return _answer_anthropic(question, context, chunks)
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER='{provider}' in .env. "
            f"Valid options: gemini, mistral, openai, anthropic"
        )


def _answer_gemini(question: str, context: str, chunks: List[dict]) -> dict:
    """Call Gemini 2.5 Flash via google-genai SDK (Python 3.14 compatible, FREE)."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise ImportError("Run: pip install google-genai")

    if not settings.gemini_api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set in .env. "
            "Get a free key at https://aistudio.google.com"
        )

    client = genai.Client(api_key=settings.gemini_api_key)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"Context:\n{context}\n\nQuestion: {question}",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=1024,
        )
    )

    answer_text = response.text
    logger.info("Answer generated | provider=gemini | chars=%d", len(answer_text))

    return {
        "answer": answer_text,
        "sources": [
            {"source": c.get("source"), "score": c.get("score", 0)}
            for c in chunks
        ]
    }


def _answer_mistral(question: str, context: str, chunks: List[dict]) -> dict:
    try:
        from mistralai import Mistral
    except (ImportError, Exception):
        raise RuntimeError(
            "mistralai is not compatible with Python 3.14. "
            "Use LLM_PROVIDER=gemini in .env instead."
        )
    if not settings.mistral_api_key:
        raise EnvironmentError(
            "MISTRAL_API_KEY is not set in .env. "
            "Get a free key at https://console.mistral.ai"
        )

    client = Mistral(api_key=settings.mistral_api_key)

    response = client.chat.complete(
        model="mistral-small-latest",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}
        ]
    )

    answer_text = response.choices[0].message.content
    logger.info("Answer generated | provider=mistral | chars=%d", len(answer_text))

    return {
        "answer": answer_text,
        "sources": [
            {"source": c.get("source"), "score": c.get("score", 0)}
            for c in chunks
        ]
    }


def _answer_openai(question: str, context: str, chunks: List[dict]) -> dict:
    """Call GPT-4o-mini via OpenAI SDK (requires paid credits)."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Run: pip install openai")

    if not settings.openai_api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set in .env")

    client = OpenAI(api_key=settings.openai_api_key)

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}
        ]
    )

    answer_text = resp.choices[0].message.content
    logger.info("Answer generated | provider=openai | chars=%d", len(answer_text))

    return {
        "answer": answer_text,
        "sources": [
            {"source": c.get("source"), "score": c.get("score", 0)}
            for c in chunks
        ]
    }


def _answer_anthropic(question: str, context: str, chunks: List[dict]) -> dict:
    """Call Claude Sonnet via Anthropic SDK (requires paid credits)."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("Run: pip install anthropic")

    if not settings.anthropic_api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set in .env. "
            "Get a key at https://console.anthropic.com"
        )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion: {question}"
        }]
    )

    answer_text = message.content[0].text
    logger.info("Answer generated | provider=anthropic | chars=%d", len(answer_text))

    return {
        "answer": answer_text,
        "sources": [
            {"source": c.get("source"), "score": c.get("score", 0)}
            for c in chunks
        ]
    }