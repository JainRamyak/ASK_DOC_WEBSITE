import logging, sys
from config import settings

def setup_logging():
    level = getattr(logging, settings.log_level, logging.INFO)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S"
    ))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(h)
    for noisy in ["urllib3","httpx","sentence_transformers","filelock"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)