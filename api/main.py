"""
api/main.py
"""
import os
import shutil
import uuid
import logging

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.pipeline import AskMyDocsPipeline
from src.utils.validators import validate_file, FileValidationError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AskMyDocs API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = AskMyDocsPipeline()


class QueryRequest(BaseModel):
    session_id: str
    question: str


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    content = await file.read()

    try:
        validate_file(file.filename, len(content))
    except FileValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session_id = str(uuid.uuid4())
    tmp_dir = f"/tmp/rag_sessions/{session_id}"
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = f"{tmp_dir}/{file.filename}"

    with open(tmp_path, "wb") as f:
        f.write(content)

    try:
        chunk_count = pipeline.ingest(tmp_dir, session_id=session_id)
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

    shutil.rmtree(tmp_dir, ignore_errors=True)

    return {
        "session_id": session_id,
        "filename": file.filename,
        "chunks": chunk_count,
        "status": "ready"
    }


@app.post("/query")
async def query_document(request: QueryRequest):
    try:
        result = pipeline.ask(request.question, session_id=request.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    pipeline.chroma_store.delete_session(session_id)
    return {"deleted": session_id}