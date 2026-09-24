"""
tests/test_embedder.py

Run with: pytest tests/test_embedder.py -v
"""
import pytest

from embedder import get_embedder
from embedder.base import BaseEmbedder
from src.utils.validators import FileValidationError, validate_file


@pytest.fixture(scope="module")
def embedder():
    return get_embedder()


# ── Basic contract ───────────────────────────────────────────────────────

def test_embedder_implements_base(embedder):
    assert isinstance(embedder, BaseEmbedder)


def test_embed_text_returns_vector(embedder):
    vec = embedder.embed_text("hello world")
    assert isinstance(vec, list)
    assert len(vec) == embedder.dimension
    assert all(isinstance(x, float) for x in vec)


def test_embed_text_empty_raises(embedder):
    with pytest.raises(ValueError):
        embedder.embed_text("")


def test_embed_text_whitespace_only_raises(embedder):
    with pytest.raises(ValueError):
        embedder.embed_text("   ")


def test_embed_batch_returns_multiple_vectors(embedder):
    vecs = embedder.embed_batch(["a", "b", "c"])
    assert len(vecs) == 3
    assert all(len(v) == embedder.dimension for v in vecs)


def test_embed_batch_empty_raises(embedder):
    with pytest.raises(ValueError):
        embedder.embed_batch([])


def test_dimension_is_positive_int(embedder):
    assert isinstance(embedder.dimension, int)
    assert embedder.dimension > 0


# ── Similarity behavior ──────────────────────────────────────────────────

def test_similarity_identical_text_is_high(embedder):
    score = embedder.similarity("the quick brown fox", "the quick brown fox")
    assert score > 0.99


def test_similarity_related_text_higher_than_unrelated(embedder):
    related = embedder.similarity("The cat sat on the mat", "A kitten rested on the rug")
    unrelated = embedder.similarity("The cat sat on the mat", "Stock markets fell today")
    assert related > unrelated


def test_similarity_is_symmetric(embedder):
    a = embedder.similarity("hello", "world")
    b = embedder.similarity("world", "hello")
    assert abs(a - b) < 1e-5


# ── File validators (no model needed, fast) ──────────────────────────────

def test_validate_file_accepts_txt():
    validate_file("notes.txt", 1024)  # should not raise


def test_validate_file_rejects_bad_extension():
    with pytest.raises(FileValidationError):
        validate_file("virus.exe", 1024)


def test_validate_file_rejects_absolute_path():
    with pytest.raises(FileValidationError):
        validate_file("/etc/passwd", 1024)


def test_validate_file_rejects_path_traversal():
    with pytest.raises(FileValidationError):
        validate_file("../../etc/passwd.txt", 1024)


def test_validate_file_rejects_oversized():
    with pytest.raises(FileValidationError):
        validate_file("big.pdf", 999_999_999)


def test_validate_file_rejects_empty():
    with pytest.raises(FileValidationError):
        validate_file("empty.txt", 0)


def test_validate_file_rejects_missing_filename():
    with pytest.raises(FileValidationError):
        validate_file("", 1024)


def test_disambiguate_filename_first_occurrence_unchanged():
    from src.utils.validators import disambiguate_filename

    seen = {}
    assert disambiguate_filename("notes.pdf", seen) == "notes.pdf"


def test_disambiguate_filename_duplicates_get_suffixed():
    from src.utils.validators import disambiguate_filename

    seen = {}
    results = [disambiguate_filename("notes.pdf", seen) for _ in range(3)]
    assert results == ["notes.pdf", "notes (1).pdf", "notes (2).pdf"]


def test_disambiguate_filename_different_names_dont_collide():
    from src.utils.validators import disambiguate_filename

    seen = {}
    a = disambiguate_filename("notes.pdf", seen)
    b = disambiguate_filename("other.txt", seen)
    assert a == "notes.pdf"
    assert b == "other.txt"
