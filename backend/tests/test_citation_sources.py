"""
tests/test_citation_sources.py

G04: the API `sources` list must line up with the `[n]` labels the LLM
sees — one numbered entry per context chunk (no dedup), with a `page`
only for PDF pages.

Run with: pytest tests/test_citation_sources.py -v

Key-free: embedder/reranker are stubbed and the provider function is
monkeypatched; no LLM or provider SDK is imported or called.
"""
import re

import pytest

import src.generation.answer_chain as answer_chain
import src.pipeline as pipeline_module
from config import settings
from embedder.base import BaseEmbedder


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

    def rerank(self, query, chunks, top_n=5):
        return [{**c, "score": 1.0 - i / 10} for i, c in enumerate(chunks[:top_n])]


@pytest.fixture
def pl(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline_module, "get_embedder", lambda: _StubEmbedder())
    monkeypatch.setattr(pipeline_module, "Reranker", _StubReranker)
    monkeypatch.setattr(settings, "chroma_persist_dir", str(tmp_path / "chroma"))
    return pipeline_module.AskMyDocsPipeline()


def _chunks():
    return [
        {"text": "a", "source": "doc.pdf#page4", "page": 4, "score": 0.9},
        {"text": "b", "source": "doc.pdf#page4", "page": 4, "score": 0.8},
        {"text": "c", "source": "https://x/y", "page": 1, "score": 0.7},
    ]


# ── AC1 / Req 8: numbered, no dedup, ordered ─────────────────────────────

def test_sources_one_entry_per_chunk_numbered():
    sources = answer_chain._sources(_chunks())
    assert [s["n"] for s in sources] == [1, 2, 3]
    assert [s["source"] for s in sources] == ["doc.pdf#page4", "doc.pdf#page4", "https://x/y"]


# ── AC2: n equals the label the LLM was shown ────────────────────────────

def test_sources_n_matches_build_context_labels():
    chunks = _chunks()
    labels = [int(m) for m in re.findall(r"^\[(\d+)\] \(source:", answer_chain._build_context(chunks), re.M)]
    assert labels == [s["n"] for s in answer_chain._sources(chunks)]


# ── AC4: source/score unchanged in meaning ───────────────────────────────

def test_sources_keep_source_and_score():
    for chunk, s in zip(_chunks(), answer_chain._sources(_chunks())):
        assert s["source"] == chunk["source"]
        assert s["score"] == chunk["score"]


# ── AC3: page only for PDF pages ─────────────────────────────────────────

@pytest.mark.parametrize(
    "chunk, expected_page",
    [
        ({"source": "doc.pdf#page4", "page": 4}, 4),
        ({"source": "a.txt", "page": 1}, None),
        ({"source": "a.md", "page": 1}, None),
        ({"source": "a.docx", "page": 1}, None),
        ({"source": "https://x/y", "page": 1}, None),
        ({"source": "https://x/y#page2", "page": 1}, None),
        ({"source": "https://x/y#page1", "page": 1}, None),
        ({"source": "old.pdf#page3"}, None),  # chunk indexed without `page`
    ],
)
def test_sources_page_only_for_pdf(chunk, expected_page):
    [s] = answer_chain._sources([{"text": "t", "score": 0.5, **chunk}])
    if expected_page is None:
        assert "page" not in s
    else:
        assert s["page"] == expected_page


# ── AC5: page survives retrieve_and_rerank ───────────────────────────────

def test_retrieve_and_rerank_carries_page(monkeypatch, pl):
    monkeypatch.setattr(
        pl.chroma_store,
        "query",
        lambda session_id, query_embedding, top_k: {
            "documents": [["t1", "t2"]],
            "metadatas": [[
                {"source": "doc.pdf#page4", "page": 4, "content_hash": "h", "chunk_index": 0},
                {"source": "a.txt"},
            ]],
        },
    )
    out = pl.retrieve_and_rerank("q", "sid", top_n=5)
    assert out[0]["page"] == 4
    assert "page" not in out[1]
    assert all("content_hash" not in c for c in out)


# ── AC6: end to end through ask() ────────────────────────────────────────

def test_ask_grounded_returns_numbered_sources(monkeypatch, pl):
    chunks = _chunks()
    monkeypatch.setattr(pl.chroma_store, "session_exists", lambda session_id: True)
    monkeypatch.setattr(pl, "retrieve_and_rerank", lambda question, session_id, top_n: chunks)
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(
        answer_chain,
        "_answer_gemini",
        lambda q, ctx, cs: {"answer": "Claim [1] and [3].", "sources": answer_chain._sources(cs)},
    )
    result = pl.ask("q", session_id="sid")
    assert result["grounded"] is True
    assert [s["n"] for s in result["sources"]] == [1, 2, 3]
    assert result["sources"][0]["page"] == 4
    assert "page" not in result["sources"][2]
