FROM python:3.11-slim

# System deps needed for PyMuPDF, chromadb, sentence-transformers, and
# the OCR fallback (tesseract-ocr). Included unconditionally so
# ENABLE_OCR=true/false is a pure env-var toggle — no separate rebuild
# needed if you decide to turn OCR on later.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libgomp1 \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# torch's default PyPI wheel on Linux/x86_64 pulls the CUDA build
# (~2GB, including NVIDIA CUDA libraries the app never uses on Render's
# CPU-only free tier). Installing the CPU-only wheel first — pinned to
# the exact version requirements.txt also pins — means the later
# `pip install -r requirements.txt` sees torch already satisfied at
# that version and skips reinstalling it, so the CUDA wheel is never
# pulled in.
RUN pip install --no-cache-dir torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu

# Install remaining Python deps (cached layer if requirements don't change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Pre-create storage dirs
RUN mkdir -p outputs/chroma /tmp/rag_sessions

# Render/Railway inject $PORT at runtime; default to 8000 for local `docker run`
ENV PORT=8000
EXPOSE $PORT

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
