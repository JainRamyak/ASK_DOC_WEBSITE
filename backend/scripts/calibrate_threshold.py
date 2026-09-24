"""
scripts/calibrate_threshold.py

RELEVANCE_THRESHOLD in .env is a heuristic, not a law of physics — the
right value depends on your documents and the kind of questions people
ask. This script helps you pick a sane value instead of guessing.

Usage:
    1. Put some real documents in a folder, e.g. docs/
    2. Edit IN_DOC_QUESTIONS and OUT_OF_DOC_QUESTIONS below to match
       your documents (questions you KNOW are answered in them, and
       questions you KNOW are not).
    3. Run: python scripts/calibrate_threshold.py docs/
    4. Look at the printed scores. Pick a threshold that sits between
       the lowest "in-doc" score and the highest "out-of-doc" score.
       Put that number in .env as RELEVANCE_THRESHOLD.
"""
import sys

sys.path.insert(0, ".")

from logger import setup_logging  # noqa: E402

setup_logging()

from src.pipeline import AskMyDocsPipeline  # noqa: E402

# EDIT THESE to match whatever documents you point this script at.
IN_DOC_QUESTIONS = [
    "Who created Python?",
    "What is FastAPI?",
]

OUT_OF_DOC_QUESTIONS = [
    "What is the capital of France?",
    "Explain quantum entanglement.",
    "Write me a poem about the ocean.",
]


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/calibrate_threshold.py <docs_directory>")
        sys.exit(1)

    directory = sys.argv[1]
    p = AskMyDocsPipeline()
    session_id = "calibration"
    p.chroma_store.delete_session(session_id)  # start clean
    p.ingest(directory, session_id=session_id)

    print(f"\n{'Expected':<12} {'Top score':<12} Question")
    print("-" * 70)

    in_scores, out_scores = [], []

    for q in IN_DOC_QUESTIONS:
        score = _top_score(p, q, session_id)
        in_scores.append(score)
        print(f"{'IN-DOC':<12} {score:<12.3f} {q}")

    for q in OUT_OF_DOC_QUESTIONS:
        score = _top_score(p, q, session_id)
        out_scores.append(score)
        print(f"{'OUT-OF-DOC':<12} {score:<12.3f} {q}")

    print("\n---")
    if in_scores and out_scores:
        lowest_in = min(in_scores)
        highest_out = max(out_scores)
        print(f"Lowest in-doc score:     {lowest_in:.3f}")
        print(f"Highest out-of-doc score: {highest_out:.3f}")
        if lowest_in > highest_out:
            suggested = (lowest_in + highest_out) / 2
            print(f"Clean separation. Suggested RELEVANCE_THRESHOLD = {suggested:.2f}")
        else:
            print(
                "WARNING: scores overlap — no single threshold perfectly "
                "separates these. Add more/better test questions, or "
                "accept some error rate at the boundary."
            )

    p.chroma_store.delete_session(session_id)


def _top_score(pipeline: "AskMyDocsPipeline", question: str, session_id: str) -> float:
    top = pipeline.retrieve_and_rerank(question, session_id, top_n=1)
    return top[0]["score"] if top else float("-inf")


if __name__ == "__main__":
    main()
