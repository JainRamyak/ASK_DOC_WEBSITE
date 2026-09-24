"""
tests/test_pipeline.py

Integration tests for the full RAG pipeline.
Run with: pytest tests/test_pipeline.py -v

NOTE: several tests here call the configured LLM provider. Make sure
LLM_PROVIDER in .env points at a provider with a valid API key before
running the full suite.
"""
import pytest

from src.generation.answer_chain import NOT_FOUND_MESSAGE
from src.pipeline import AskMyDocsPipeline

TEST_SESSION = "pytest-session"


@pytest.fixture(scope="module")
def pipeline():
    p = AskMyDocsPipeline()
    p.chroma_store.delete_session(TEST_SESSION)  # start from a clean session
    p.ingest("docs/", session_id=TEST_SESSION)
    yield p
    p.chroma_store.delete_session(TEST_SESSION)  # clean up after the module


# ── Ingestion ────────────────────────────────────────────────────────────

def test_ingest_creates_session(pipeline):
    assert pipeline.chroma_store.session_exists(TEST_SESSION)


def test_ingest_returns_chunk_count():
    p = AskMyDocsPipeline()
    p.chroma_store.delete_session("count-check")
    count = p.ingest("docs/", session_id="count-check")
    assert isinstance(count, int)
    assert count > 0
    p.chroma_store.delete_session("count-check")


# ── Retrieval ────────────────────────────────────────────────────────────

def test_retrieval_returns_results(pipeline):
    from config import settings

    q_vec = pipeline.embedder.embed_text("Who created Python?")
    results = pipeline.chroma_store.query(
        session_id=TEST_SESSION, query_embedding=q_vec, top_k=settings.top_k * 4
    )
    assert len(results["documents"][0]) > 0


def test_retrieval_chunks_have_source_metadata(pipeline):
    from config import settings

    q_vec = pipeline.embedder.embed_text("What is FastAPI?")
    results = pipeline.chroma_store.query(
        session_id=TEST_SESSION, query_embedding=q_vec, top_k=settings.top_k * 4
    )
    for meta in results["metadatas"][0]:
        assert "source" in meta


# ── Answer generation ────────────────────────────────────────────────────

def test_ask_returns_answer(pipeline):
    result = pipeline.ask("Who created Python?", session_id=TEST_SESSION)
    assert "answer" in result
    assert len(result["answer"]) > 0


def test_ask_returns_sources_when_grounded(pipeline):
    result = pipeline.ask("Who created Python?", session_id=TEST_SESSION)
    if result["grounded"]:
        assert len(result["sources"]) > 0


def test_ask_answer_contains_citation_when_grounded(pipeline):
    result = pipeline.ask("Who created Python?", session_id=TEST_SESSION)
    if result["grounded"]:
        assert "[1]" in result["answer"] or "[2]" in result["answer"]


def test_ask_empty_question_handled(pipeline):
    result = pipeline.ask("", session_id=TEST_SESSION)
    assert result["answer"] == NOT_FOUND_MESSAGE
    assert result["grounded"] is False


def test_ask_unknown_session_handled(pipeline):
    result = pipeline.ask("Anything?", session_id="session-that-does-not-exist")
    assert result["grounded"] is False


def test_ask_unrelated_question_is_rejected(pipeline):
    """The core product guarantee: a question unrelated to the uploaded
    document must NOT be answered from the LLM's own knowledge."""
    result = pipeline.ask(
        "What is the boiling point of mercury in Kelvin?", session_id=TEST_SESSION
    )
    assert result["grounded"] is False
    assert result["answer"] == NOT_FOUND_MESSAGE


# ── Loader ───────────────────────────────────────────────────────────────

def test_loader_reads_files():
    from src.ingestion.loader import load_documents

    docs = load_documents("docs/")
    assert len(docs) >= 1
    assert all("text" in d and "source" in d for d in docs)


def test_loader_reads_pdf():
    from src.ingestion.loader import load_documents

    docs = load_documents("docs/")
    pdf_docs = [d for d in docs if ".pdf" in d["source"]]
    assert len(pdf_docs) > 0


# ── Chunker ──────────────────────────────────────────────────────────────

def test_chunker_splits_long_text():
    from src.ingestion.chunker import chunk_documents

    long_doc = [{"text": "word " * 500, "source": "test.txt"}]
    chunks = chunk_documents(long_doc)
    assert len(chunks) > 1


def test_chunker_empty_input_returns_empty():
    from src.ingestion.chunker import chunk_documents

    assert chunk_documents([]) == []
