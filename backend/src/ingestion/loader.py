"""
src/ingestion/loader.py
Supported formats: .txt, .md, .pdf, .docx
"""
import logging
from pathlib import Path
from typing import List
from docx import Document as DocxDocument

logger = logging.getLogger(__name__)


def load_documents(directory: str) -> List[dict]:
    docs = []
    path = Path(directory)

    for filepath in sorted(path.rglob("*")):
        if filepath.suffix == ".pdf":
            docs.extend(_load_pdf(filepath))
        elif filepath.suffix in (".txt", ".md"):
            docs.extend(_load_text(filepath))
        elif filepath.suffix == ".docx":
            docs.extend(_load_docx(filepath))

    logger.info("Loaded %d pages from %s", len(docs), directory)
    return docs


def _load_text(filepath: Path) -> List[dict]:
    try:
        text = filepath.read_text(encoding="utf-8").strip()
        if not text:
            return []
        return [{"text": text, "source": filepath.name}]
    except Exception as e:
        logger.warning("Failed to load %s: %s", filepath, e)
        return []


def _load_docx(filepath: Path) -> List[dict]:
    try:
        doc = DocxDocument(str(filepath))
        text = "\n".join(
            para.text for para in doc.paragraphs if para.text.strip()
        )
        if not text:
            return []
        return [{"text": text, "source": filepath.name}]
    except Exception as e:
        logger.warning("Failed to load DOCX %s: %s", filepath, e)
        return []


def _load_pdf(filepath: Path) -> List[dict]:
    try:
        import pymupdf
    except ImportError:
        raise ImportError("Run: pip install pymupdf")

    docs = []
    try:
        pdf = pymupdf.open(str(filepath))
        for page_num, page in enumerate(pdf, 1):
            text = page.get_text().strip()
            if text:
                docs.append({
                    "text": text,
                    "source": f"{filepath.name}#page{page_num}"
                })
        pdf.close()
        logger.info("PDF loaded: %s | %d pages", filepath.name, len(docs))
    except Exception as e:
        logger.warning("Failed to load PDF %s: %s", filepath, e)

    return docs