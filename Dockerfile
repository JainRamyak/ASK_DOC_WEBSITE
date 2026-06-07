FROM python:3.11-slim

# System deps needed for PyMuPDF, chromadb, and sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cached layer if requirements don't change)
COPY backend/requirements.prod.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ .

# Pre-create chroma storage dir
RUN mkdir -p outputs/chroma /tmp/rag_sessions

# PORT is injected by Railway at runtime; default to 8000 for local docker run
ENV PORT=8000

EXPOSE $PORT

# railway.toml startCommand overrides this with the actual $PORT value
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
