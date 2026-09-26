"""
src/ingestion/loader.py

Supported formats: .txt, .md, .pdf, .docx

PDF pages with no text layer (scanned documents/images) fall back to
OCR via pytesseract, if ENABLE_OCR=true and the tesseract binary is
installed (the Dockerfile installs it unconditionally, so this is a
pure config toggle in a Docker deployment). Off by default — OCR is
slow (roughly 1-3s/page) and most PDFs don't need it.
"""
import logging
from pathlib import Path
from typing import List

from config import settings

logger = logging.getLogger(__name__)

# Why a supported file contributed no text (see LoadedDocuments.skipped).
UNREADABLE = "unreadable"  # could not be opened/parsed
NO_TEXT = "no_text"        # read fine, but nothing extractable


class _UnreadableFile(Exception):
    """A supported file that could not be opened or parsed."""


class LoadedDocuments(list):
    """The list of document dicts `load_documents` has always returned,
    plus `.skipped`: {on-disk filename: UNREADABLE | NO_TEXT} for every
    supported file that produced no text. It is a plain list for every
    existing caller; the extra attribute lets /upload report truthfully
    without changing `load_documents`'s signature or return type."""

    def __init__(self, *args):
        super().__init__(*args)
        self.skipped: dict = {}


def load_documents(directory: str) -> LoadedDocuments:
    """Load every supported file in `directory` (recursively) into
    a flat list of {"text": ..., "source": ..., "file": ...} dicts, one
    per page (for PDFs) or per file (for everything else). `file` is the
    on-disk filename the text came from."""
    docs = LoadedDocuments()
    path = Path(directory)

    for filepath in sorted(path.rglob("*")):
        if not filepath.is_file():
            continue

        suffix = filepath.suffix.lower()
        if suffix == ".pdf":
            loader = _load_pdf
        elif suffix in (".txt", ".md"):
            loader = _load_text
        elif suffix == ".docx":
            loader = _load_docx
        else:
            logger.debug("Skipping unsupported file: %s", filepath.name)
            continue

        try:
            file_docs = loader(filepath)
        except _UnreadableFile:
            docs.skipped[filepath.name] = UNREADABLE
            continue

        if not file_docs:
            docs.skipped[filepath.name] = NO_TEXT
            continue

        for d in file_docs:
            d["file"] = filepath.name
        docs.extend(file_docs)

    logger.info("Loaded %d page(s)/section(s) from %s", len(docs), directory)
    return docs


def _load_text(filepath: Path) -> List[dict]:
    try:
        text = filepath.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            return []
        return [{"text": text, "source": filepath.name}]
    except Exception as e:
        logger.warning("Failed to load %s: %s", filepath, e)
        raise _UnreadableFile(filepath.name) from e


def _load_docx(filepath: Path) -> List[dict]:
    try:
        from docx import Document as DocxDocument
    except ImportError:
        raise ImportError("Run: pip install python-docx")

    try:
        doc = DocxDocument(str(filepath))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        if not text:
            return []
        return [{"text": text, "source": filepath.name}]
    except Exception as e:
        logger.warning("Failed to load DOCX %s: %s", filepath, e)
        raise _UnreadableFile(filepath.name) from e


def _load_pdf(filepath: Path) -> List[dict]:
    try:
        import pymupdf
    except ImportError:
        raise ImportError("Run: pip install pymupdf")

    docs: List[dict] = []
    try:
        pdf = pymupdf.open(str(filepath))
        ocr_pages = 0
        for page_num, page in enumerate(pdf, 1):
            text = page.get_text().strip()
            if not text and settings.enable_ocr:
                text = _ocr_page(page)
                if text:
                    ocr_pages += 1
            if text:
                docs.append({
                    "text": text,
                    "source": f"{filepath.name}#page{page_num}",
                    "page": page_num,
                })
        pdf.close()
        logger.info(
            "PDF loaded: %s | %d page(s) with text%s",
            filepath.name, len(docs),
            f" ({ocr_pages} via OCR)" if ocr_pages else "",
        )
    except Exception as e:
        logger.warning("Failed to load PDF %s: %s", filepath, e)
        # Keep pages already extracted; only a file that yielded nothing
        # before failing counts as unreadable.
        if not docs:
            raise _UnreadableFile(filepath.name) from e
    return docs


def _ocr_page(page) -> str:
    """Render a PDF page to an image and OCR it. Only called when the
    page's text layer was empty and ENABLE_OCR=true. Returns "" (not an
    exception) on any failure — a page that can't be OCR'd just gets
    skipped, it shouldn't fail the whole upload."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.warning(
            "ENABLE_OCR=true but pytesseract/Pillow aren't installed. "
            "Run: pip install pytesseract Pillow — and install the "
            "tesseract system package (see requirements.txt comment)."
        )
        return ""

    try:
        pix = page.get_pixmap(dpi=200)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        return pytesseract.image_to_string(img).strip()
    except Exception as e:
        logger.warning("OCR failed on a page: %s", e)
        return ""
