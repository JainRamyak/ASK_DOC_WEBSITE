import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import settings

logger = logging.getLogger(__name__)


def chunk_documents(docs: list[dict]) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []
    for doc in docs:
        for i, text in enumerate(splitter.split_text(doc["text"])):
            chunk = {
                "text": text,
                "source": doc["source"],
                "page": doc.get("page", 1),
                "chunk_index": i,
            }
            # G27 dedup: carry the source doc's content identity onto each
            # of its chunks, if it has one. Callers that don't stamp
            # `content_hash` on their docs (e.g. existing tests) get
            # chunks with no such key, unchanged from before.
            if "content_hash" in doc:
                chunk["content_hash"] = doc["content_hash"]
            chunks.append(chunk)

    logger.info("Chunked %d doc section(s) into %d chunk(s)", len(docs), len(chunks))
    return chunks
