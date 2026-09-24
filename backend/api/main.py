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
from src.ingestion.web_loader import URLValidationError
from src.pipeline import AskMyDocsPipeline
from src.utils.rate_limit import InMemoryRateLimiter
from src.utils.validators import FileValidationError, disambiguate_filename, validate_file

setup_logging()
logger = logging.getLogger(__name__)


async def _session_cleanup_loop(pipeline: "AskMyDocsPipeline"):
    """Runs for the lifetime of the process, deleting expired sessions
    every hour. See config.settings.session_ttl_hours. Turns
    ChromaStore.cleanup_expired() from an unwired method into something
    that actually runs, instead of requiring a separate cron job."""
    while True:
        try:
            await run_in_threadpool(pipeline.chroma_store.cleanup_expired, settings.session_ttl_hours)
        except Exception:
            logger.exception("Session cleanup pass failed (will retry next hour)")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(_session_cleanup_loop(pipeline))
    logger.info(
        "Session cleanup scheduled | ttl_hours=%d | interval=hourly",
        settings.session_ttl_hours,
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
    tmp_dir = f"/tmp/rag_sessions/{session_id}"
    os.makedirs(tmp_dir, exist_ok=True)

    saved_filenames = []
    seen_names: dict = {}
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

            tmp_path = os.path.join(tmp_dir, disk_name)
            with open(tmp_path, "wb") as f:
                f.write(content)
            saved_filenames.append(file.filename)

        chunk_count = await run_in_threadpool(pipeline.ingest, tmp_dir, session_id=session_id)

    except HTTPException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except Exception as e:
        logger.exception("Upload ingestion failed")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        _cleanup_if_new(session_id, is_new_session)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

    shutil.rmtree(tmp_dir, ignore_errors=True)

    if chunk_count == 0:
        _cleanup_if_new(session_id, is_new_session)
        raise HTTPException(
            status_code=400,
            detail="No readable text was found in the uploaded file(s).",
        )

    return {
        "session_id": session_id,
        "filenames": saved_filenames,
        "chunks": chunk_count,
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
        chunk_count = await run_in_threadpool(
            pipeline.ingest_url, request.url.strip(), session_id=session_id
        )
    except URLValidationError as e:
        _cleanup_if_new(session_id, is_new_session)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("URL ingestion failed")
        _cleanup_if_new(session_id, is_new_session)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

    if chunk_count == 0:
        _cleanup_if_new(session_id, is_new_session)
        raise HTTPException(
            status_code=400,
            detail="No readable text was found at that URL.",
        )

    return {
        "session_id": session_id,
        "filenames": [request.url.strip()],
        "chunks": chunk_count,
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
