"""
api/main.py
"""
import asyncio
import json
import logging
import os
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from config import settings
from logger import setup_logging
from src.ingestion.loader import NO_TEXT, UNREADABLE
from src.ingestion.web_loader import URLValidationError
from src.pipeline import AskMyDocsPipeline
from src.utils.rate_limit import InMemoryRateLimiter
from src.utils.validators import FileValidationError, disambiguate_filename, validate_file

setup_logging()
logger = logging.getLogger(__name__)


async def _session_cleanup_loop(pipeline: "AskMyDocsPipeline"):
    """Runs for the lifetime of the process, deleting expired sessions
    every hour. See config.settings.session_ttl_hours (idle timeout) and
    session_max_lifetime_hours (absolute cap from creation). Turns
    ChromaStore.cleanup_expired() from an unwired method into something
    that actually runs, instead of requiring a separate cron job."""
    while True:
        try:
            await run_in_threadpool(
                pipeline.chroma_store.cleanup_expired,
                settings.session_ttl_hours,
                settings.session_max_lifetime_hours,
            )
        except Exception:
            logger.exception("Session cleanup pass failed (will retry next hour)")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(_session_cleanup_loop(pipeline))
    logger.info(
        "Session cleanup scheduled | ttl_hours=%d | max_lifetime_hours=%d | interval=hourly",
        settings.session_ttl_hours,
        settings.session_max_lifetime_hours,
    )
    yield
    cleanup_task.cancel()


pipeline = AskMyDocsPipeline()

app = FastAPI(title="AskMyDocs API", version="2.2.0", lifespan=lifespan)

app.add_middleware(
    InMemoryRateLimiter,
    requests_per_window=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)


def _cleanup_if_new(session_id: str, is_new_session: bool) -> None:
    """Delete a just-created, now-orphaned session so a failed upload
    doesn't leave an empty collection behind."""
    if is_new_session:
        pipeline.chroma_store.delete_session(session_id)


def _validate_client_session_id(session_id: str) -> None:
    """A client-supplied session_id is only ever a UUID this server
    generated in an earlier response — reject anything else before it's
    used to build a filesystem path or a ChromaDB collection name."""
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id.")


# User-facing reasons a file was skipped, keyed by loader reason code.
# Fixed strings on purpose: never exception text, paths or staging names.
SKIP_MESSAGES = {
    UNREADABLE: "Couldn't be read — the file may be corrupt or not a valid document.",
    NO_TEXT: (
        "No text could be extracted — it may be empty, made of scanned "
        "images, or contain only tables."
    ),
}


class QueryRequest(BaseModel):
    session_id: str
    question: str
    # Prior user questions in this session, most recent last. Only acted
    # on if ENABLE_QUERY_REWRITING=true — harmless to send otherwise.
    history: Optional[List[str]] = None


class UploadURLRequest(BaseModel):
    url: str
    session_id: Optional[str] = None


class FeedbackRequest(BaseModel):
    session_id: str
    question: str
    answer: str
    helpful: bool


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.2.0"}


@app.post("/upload")
async def upload_documents(
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Form(default=None),
):
    """Upload one or more files. Pass `session_id` to add files to an
    existing session; omit it to start a new session."""
    if len(files) > settings.max_files_per_upload:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Max {settings.max_files_per_upload} per upload.",
        )

    if session_id is not None:
        _validate_client_session_id(session_id)

    is_new_session = session_id is None
    session_id = session_id or str(uuid.uuid4())
    # Staged per request, not per session: ingest() scans the whole directory
    # and cleanup removes it, so a shared per-session dir lets overlapping
    # uploads to one session ingest and delete each other's files.
    tmp_dir = f"/tmp/rag_sessions/{uuid.uuid4().hex}"
    os.makedirs(tmp_dir, exist_ok=True)

    staged = []  # (original filename, on-disk name), in upload order
    seen_names: dict = {}
    used_disk_names: set = set()
    try:
        for file in files:
            content = await file.read()
            try:
                validate_file(file.filename, len(content))
            except FileValidationError as e:
                raise HTTPException(status_code=400, detail=f"{file.filename}: {e}")

            # Disambiguate duplicate filenames within one upload so the
            # second file doesn't silently overwrite the first's temp
            # copy before ingestion. validate_file() has already ruled
            # out path traversal above — this only handles same-name
            # collisions within one batch, nothing path-related.
            disk_name = disambiguate_filename(file.filename, seen_names)
            # A later file literally named like an earlier disambiguated
            # copy ("a (1).txt") would land on the same path; keep asking.
            while disk_name in used_disk_names:
                disk_name = disambiguate_filename(file.filename, seen_names)
            used_disk_names.add(disk_name)

            tmp_path = os.path.join(tmp_dir, disk_name)
            with open(tmp_path, "wb") as f:
                f.write(content)
            staged.append((file.filename, disk_name))

        result = await run_in_threadpool(
            pipeline.ingest_with_report, tmp_dir, session_id=session_id
        )

    except HTTPException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except Exception as e:
        logger.exception("Upload ingestion failed")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        _cleanup_if_new(session_id, is_new_session)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

    shutil.rmtree(tmp_dir, ignore_errors=True)

    if result.chunks == 0 and not result.already_indexed:
        _cleanup_if_new(session_id, is_new_session)
        raise HTTPException(
            status_code=400,
            detail="No readable text was found in the uploaded file(s).",
        )

    # Every uploaded file lands in exactly one list. A file with no recorded
    # outcome is treated as "no text" rather than claimed as indexed.
    filenames = []
    already_indexed = []
    skipped = []
    for original, disk_name in staged:
        if disk_name in result.indexed:
            filenames.append(original)
        elif disk_name in result.already_indexed:
            already_indexed.append(
                {"filename": original, "hash": result.already_indexed[disk_name]}
            )
        else:
            reason = result.skipped.get(disk_name, NO_TEXT)
            skipped.append(
                {"filename": original, "reason": reason, "message": SKIP_MESSAGES[reason]}
            )

    return {
        "session_id": session_id,
        "filenames": filenames,
        "skipped": skipped,
        "already_indexed": already_indexed,
        "chunks": result.chunks,
        "status": "ready",
    }


@app.post("/upload-url")
async def upload_url(request: UploadURLRequest):
    """Fetch a live URL and ingest it, same session semantics as /upload:
    pass `session_id` to add it to an existing session, omit it to start
    a new one."""
    if not request.url or not request.url.strip():
        raise HTTPException(status_code=400, detail="url is required")

    if request.session_id is not None:
        _validate_client_session_id(request.session_id)

    is_new_session = request.session_id is None
    session_id = request.session_id or str(uuid.uuid4())

    try:
        result = await run_in_threadpool(
            pipeline.ingest_url, request.url.strip(), session_id=session_id
        )
    except URLValidationError as e:
        _cleanup_if_new(session_id, is_new_session)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("URL ingestion failed")
        _cleanup_if_new(session_id, is_new_session)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

    if result.chunks == 0 and not result.already_indexed:
        _cleanup_if_new(session_id, is_new_session)
        raise HTTPException(
            status_code=400,
            detail="No readable text was found at that URL.",
        )

    already_indexed = [
        {"filename": url, "hash": h} for url, h in result.already_indexed.items()
    ]

    return {
        "session_id": session_id,
        "filenames": [request.url.strip()] if result.indexed else [],
        "already_indexed": already_indexed,
        "chunks": result.chunks,
        "status": "ready",
    }


@app.post("/query")
async def query_document(request: QueryRequest):
    if not request.session_id or not request.question:
        raise HTTPException(status_code=400, detail="session_id and question are required")

    if len(request.question) > settings.max_question_length:
        raise HTTPException(
            status_code=400,
            detail=f"Question too long ({len(request.question)} chars). "
                    f"Max allowed: {settings.max_question_length}",
        )

    _validate_client_session_id(request.session_id)

    try:
        result = await run_in_threadpool(
            pipeline.ask, request.question, session_id=request.session_id, history=request.history
        )
    except Exception as e:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail=str(e))

    return result


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    _validate_client_session_id(session_id)
    deleted = pipeline.chroma_store.delete_session(session_id)
    return {"deleted": session_id, "success": deleted}


@app.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    """Thumbs up/down on an answer. Appends to a local JSONL file —
    deliberately minimal, no database. Same caveat as the rest of local
    storage on this deployment: on Render's free tier with no
    persistent disk, this file doesn't survive a restart."""
    os.makedirs("outputs", exist_ok=True)
    entry = request.model_dump()
    entry["timestamp"] = time.time()
    try:
        with open("outputs/feedback.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        logger.warning("Could not write feedback: %s", e)
        raise HTTPException(status_code=500, detail="Could not record feedback")
    return {"status": "recorded"}
