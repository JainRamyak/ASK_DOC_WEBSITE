import logging
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config import settings

logger = logging.getLogger(__name__)

def chunk_documents(docs: list[dict]) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    chunks = []
    for doc in docs:
        for i, text in enumerate(splitter.split_text(doc["text"])):
            chunks.append({
                "text": text,
                "source": doc["source"],
                "page": doc.get("page", 1),
                "chunk_index": i,
            })
    logger.info("Chunked %d docs into %d chunks", len(docs), len(chunks))
    return chunks