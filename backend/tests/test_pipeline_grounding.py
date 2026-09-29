"""
tests/test_pipeline_grounding.py

G03: AskMyDocsPipeline.ask() must not report grounded:true when the
LLM's own answer text is a refusal (equals NOT_FOUND_MESSAGE after
.strip()) — previously grounded was hard-set True for any post-gate
answer() call regardless of content.

Run with: pytest tests/test_pipeline_grounding.py -v

Key-free: embedder and reranker are stubbed (never loaded/called, since
retrieve_and_rerank is monkeypatched directly on the instance), and
pipeline_module.answer is monkeypatched to return a constructed dict —
no LLM/provider SDK is imported or called.
"""
import pytest

import src.pipeline as pipeline_module
from config import settings
from embedder.base import BaseEmbedder
from src.generation.answer_chain import NOT_FOUND_MESSAGE


class _StubEmbedder(BaseEmbedder):
    @property
    def dimension(self) -> int:
        return 8

    def embed_text(self, text):
        return [0.1] * 8

    def embed_batch(self, texts):
        return [self.embed_text(t) for t in texts]


class _StubReranker:
    def __init__(self, *args, **kwargs):
        pass


# ── fixture ──────────────────────────────────────────────────────────────

@pytest.fixture
def pl(monkeypatch, tmp_path):
    """A real AskMyDocsPipeline with heavy deps stubbed (repo convention,
    see test_upload_concurrency.py) and a fresh, isolated Chroma dir.
    session_exists and retrieve_and_rerank are patched per-test so ask()
    reaches the answer()-call site without a real session or embedder."""
    monkeypatch.setattr(pipeline_module, "get_embedder", lambda: _StubEmbedder())
    monkeypatch.setattr(pipeline_module, "Reranker", _StubReranker)
    monkeypatch.setattr(settings, "chroma_persist_dir", str(tmp_path / "chroma"))
    return pipeline_module.AskMyDocsPipeline()


def _pass_gate(monkeypatch, pl, chunks=None):
    """Makes ask() treat the session as existing and the retrieval gate
    as passed, with a score well above any realistic relevance_threshold."""
    monkeypatch.setattr(pl.chroma_store, "session_exists", lambda session_id: True)
    fake_chunks = chunks if chunks is not None else [{"text": "x", "source": "doc.pdf", "score": 1.0}]
    monkeypatch.setattr(pl, "retrieve_and_rerank", lambda question, session_id, top_n: fake_chunks)


# ── AC1: exact-match refusal ────────────────────────────────────────────

def test_exact_refusal_flips_grounded_false_and_empties_sources(monkeypatch, pl):
    _pass_gate(monkeypatch, pl)
    monkeypatch.setattr(
        pipeline_module, "answer",
        lambda q, chunks: {"answer": NOT_FOUND_MESSAGE, "sources": [{"source": "doc.pdf", "score": 1.0}]},
    )

    result = pl.ask("some question", session_id="s1")

    assert result == {"answer": NOT_FOUND_MESSAGE, "sources": [], "grounded": False}


# ── AC2: whitespace-padded refusal still caught ─────────────────────────

def test_whitespace_padded_refusal_still_caught(monkeypatch, pl):
    _pass_gate(monkeypatch, pl)
    monkeypatch.setattr(
        pipeline_module, "answer",
        lambda q, chunks: {"answer": f"  {NOT_FOUND_MESSAGE}  ", "sources": [{"source": "doc.pdf", "score": 1.0}]},
    )

    result = pl.ask("some question", session_id="s1")

    assert result == {"answer": NOT_FOUND_MESSAGE, "sources": [], "grounded": False}


# ── AC3: genuine answer unaffected ──────────────────────────────────────

def test_genuine_answer_stays_grounded_true(monkeypatch, pl):
    _pass_gate(monkeypatch, pl)
    real_sources = [{"source": "doc.pdf", "score": 1.0}]
    monkeypatch.setattr(
        pipeline_module, "answer",
        lambda q, chunks: {"answer": "The answer is 42 [1].", "sources": real_sources},
    )

    result = pl.ask("some question", session_id="s1")

    assert result == {"answer": "The answer is 42 [1].", "sources": real_sources, "grounded": True}


# ── AC4: substring containing NOT_FOUND_MESSAGE is NOT treated as refusal ─

def test_refusal_text_as_substring_is_treated_as_real_answer(monkeypatch, pl):
    _pass_gate(monkeypatch, pl)
    padded = NOT_FOUND_MESSAGE + " [1]"
    real_sources = [{"source": "doc.pdf", "score": 1.0}]
    monkeypatch.setattr(
        pipeline_module, "answer",
        lambda q, chunks: {"answer": padded, "sources": real_sources},
    )

    result = pl.ask("some question", session_id="s1")

    assert result == {"answer": padded, "sources": real_sources, "grounded": True}


# ── AC5: gate-level rejection unchanged ─────────────────────────────────

def test_gate_rejection_unchanged(monkeypatch, pl):
    monkeypatch.setattr(pl.chroma_store, "session_exists", lambda session_id: True)
    monkeypatch.setattr(pl, "retrieve_and_rerank", lambda question, session_id, top_n: [])

    result = pl.ask("some question", session_id="s1")

    assert result == {"answer": NOT_FOUND_MESSAGE, "sources": [], "grounded": False}
    assert "reason" not in result


# ── AC6: no_session unchanged ────────────────────────────────────────────

def test_no_session_unchanged(monkeypatch, pl):
    monkeypatch.setattr(pl.chroma_store, "session_exists", lambda session_id: False)

    result = pl.ask("some question", session_id="missing")

    assert result["grounded"] is False
    assert result["sources"] == []
    assert result["reason"] == "no_session"
