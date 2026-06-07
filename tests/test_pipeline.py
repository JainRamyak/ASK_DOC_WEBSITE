"""
tests/test_pipeline.py

Integration tests for the full RAG pipeline.
Run with: pytest tests/test_pipeline.py -v
"""
import pytest
from src.pipeline import AskMyDocsPipeline


@pytest.fixture(scope="module")
def pipeline():
    p = AskMyDocsPipeline()
    p.ingest("docs/")
    return p


# ── Ingestion ─────────────────────────────────────────────────────
def test_ingest_loads_chunks(pipeline):
    assert pipeline.vec_store.size > 0

def test_ingest_bm25_built(pipeline):
    assert pipeline.bm25_store is not None


# ── Retrieval ─────────────────────────────────────────────────────
def test_retrieval_returns_results(pipeline):
    from src.retrieval.hybrid_retriever import hybrid_search
    from config import settings
    q_vec = pipeline.embedder.embed_text("Who created Python?")
    results = hybrid_search("Who created Python?", q_vec,
                            pipeline.vec_store, pipeline.bm25_store,
                            top_k=settings.top_k * 4)
    assert len(results) > 0

def test_retrieval_chunks_have_required_keys(pipeline):
    from src.retrieval.hybrid_retriever import hybrid_search
    from config import settings
    q_vec = pipeline.embedder.embed_text("What is FastAPI?")
    results = hybrid_search("What is FastAPI?", q_vec,
                            pipeline.vec_store, pipeline.bm25_store,
                            top_k=settings.top_k * 4)
    for chunk in results:
        assert "text" in chunk
        assert "source" in chunk


# ── Answer generation ─────────────────────────────────────────────
def test_ask_returns_answer(pipeline):
    result = pipeline.ask("Who created Python?")
    assert "answer" in result
    assert len(result["answer"]) > 0

def test_ask_returns_sources(pipeline):
    result = pipeline.ask("Who created Python?")
    assert "sources" in result
    assert len(result["sources"]) > 0

def test_ask_answer_contains_citation(pipeline):
    result = pipeline.ask("Who created Python?")
    assert "[1]" in result["answer"] or "[2]" in result["answer"]

def test_ask_empty_question_handled(pipeline):
    result = pipeline.ask("")
    assert "answer" in result


# ── Loader ────────────────────────────────────────────────────────
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


# ── Chunker ───────────────────────────────────────────────────────
def test_chunker_splits_long_text():
    from src.ingestion.chunker import chunk_documents
    long_doc = [{"text": "word " * 500, "source": "test.txt"}]
    chunks = chunk_documents(long_doc)
    assert len(chunks) > 1


def test_ingest_loads_chunks(pipeline):
    assert pipeline.chroma_store is not None

def test_ingest_bm25_built(pipeline):
    # BM25 replaced by ChromaDB — verify chroma collection exists
    collection = pipeline.chroma_store.get_or_create_collection("default")
    assert collection is not None

def test_retrieval_returns_results(pipeline):
    from config import settings
    q_vec = pipeline.embedder.embed_text("Who created Python?")
    results = pipeline.chroma_store.query(
        session_id="default",
        query_embedding=q_vec,
        top_k=settings.top_k * 4
    )
    assert len(results["documents"][0]) > 0

def test_retrieval_chunks_have_required_keys(pipeline):
    from config import settings
    q_vec = pipeline.embedder.embed_text("What is FastAPI?")
    results = pipeline.chroma_store.query(
        session_id="default",
        query_embedding=q_vec,
        top_k=settings.top_k * 4
    )
    for meta in results["metadatas"][0]:
        assert "source" in meta