import logging
import sys

from config import settings


def setup_logging() -> None:
    level = getattr(logging, settings.log_level, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    for noisy in ("urllib3", "httpx", "sentence_transformers", "filelock", "chromadb"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
