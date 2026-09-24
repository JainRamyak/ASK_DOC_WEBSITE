import os

from config import settings

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


class FileValidationError(Exception):
    pass


def validate_file(filename: str, size_bytes: int) -> None:
    if not filename:
        raise FileValidationError("Filename is missing.")

    # Reject path traversal / absolute paths before this filename is ever
    # joined onto a server-side directory (api/main.py writes it to
    # tmp_dir/filename). Covers "/etc/passwd", "../../x", and "a/../../x"
    # alike — os.path.basename() strips any directory component, so if
    # the result differs from the original, something was trying to
    # escape tmp_dir.
    if (
        os.path.basename(filename) != filename
        or filename in (".", "..")
        or "\\" in filename
    ):
        raise FileValidationError(f"Invalid filename: '{filename}'")

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f"File type '{ext}' not supported. Allowed: {sorted(ALLOWED_EXTENSIONS)}"
        )

    size_mb = size_bytes / (1024 * 1024)
    if size_mb > settings.max_file_size_mb:
        raise FileValidationError(
            f"File too large ({size_mb:.1f}MB). Max allowed: {settings.max_file_size_mb}MB"
        )

    if size_bytes == 0:
        raise FileValidationError("File is empty.")


def disambiguate_filename(filename: str, seen_names: dict) -> str:
    """Given a filename and a running {name: count} dict shared across
    one upload batch, returns a disk-safe name that won't collide with
    an earlier file of the same name in the same batch — "notes.pdf",
    "notes (1).pdf", "notes (2).pdf", etc. Mutates `seen_names`. Call
    this AFTER validate_file() — it only handles duplicate names, not
    path safety, which validate_file already covers."""
    if filename in seen_names:
        seen_names[filename] += 1
        stem, ext = os.path.splitext(filename)
        return f"{stem} ({seen_names[filename]}){ext}"
    seen_names[filename] = 0
    return filename
