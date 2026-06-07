import pytest
import numpy as np
from embedder.local_embedder import LocalEmbedder


@pytest.fixture(scope="module")
def embedder():
    return LocalEmbedder()


def cosine(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def test_embed_text_returns_list(embedder):
    result = embedder.embed_text("hello world")
    assert isinstance(result, list)


def test_embed_text_correct_dimension(embedder):
    result = embedder.embed_text("hello world")
    assert len(result) == embedder.dimension


def test_embed_batch_correct_count(embedder):
    results = embedder.embed_batch(["one", "two", "three"])
    assert len(results) == 3
    assert all(len(v) == embedder.dimension for v in results)


def test_all_values_are_floats(embedder):
    result = embedder.embed_text("testing floats")
    assert all(isinstance(v, float) for v in result)


def test_similar_texts_outscore_different(embedder):
    sim = cosine(
        embedder.embed_text("The cat sat on the mat"),
        embedder.embed_text("A kitten rested on the rug")
    )
    diff = cosine(
        embedder.embed_text("The cat sat on the mat"),
        embedder.embed_text("Stock markets fell today")
    )
    assert sim > diff, f"similar={sim:.4f} must beat different={diff:.4f}"

def test_different_texts_score_low(embedder):
    score = cosine(
        embedder.embed_text("The cat sat on the mat"),
        embedder.embed_text("Stock markets fell sharply today")
    )
    assert score < 0.5, f"Expected < 0.5, got {score:.4f}"


def test_identical_texts_score_near_one(embedder):
    text = "machine learning is transforming the world"
    score = cosine(
        embedder.embed_text(text),
        embedder.embed_text(text)
    )
    assert score > 0.999


def test_empty_string_raises(embedder):
    with pytest.raises(ValueError):
        embedder.embed_text("")


def test_whitespace_only_raises(embedder):
    with pytest.raises(ValueError):
        embedder.embed_text("   ")


def test_empty_batch_raises(embedder):
    with pytest.raises(ValueError):
        embedder.embed_batch([])


def test_similarity_method_in_range(embedder):
    score = embedder.similarity("deep learning", "neural networks")
    assert 0.0 <= score <= 1.0


def test_similarity_method_high_for_related(embedder):
    score = embedder.similarity(
        "Python programming language",
        "coding in Python"
    )
    assert score > 0.7