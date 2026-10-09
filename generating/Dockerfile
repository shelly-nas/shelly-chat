FROM python:3.11-slim

# Copy uv from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install CPU-only torch before the rest to avoid pulling CUDA wheels (~2 GB)
RUN uv pip install --no-cache-dir --system \
    torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining Python dependencies
RUN uv pip install --no-cache-dir --system -r requirements.txt

# qdrant-client 1.9.x ships qdrant_fastembed.py without IDF_EMBEDDING_MODELS,
# which llama-index-vector-stores-qdrant imports at module load time.
# The app does not use IDF/sparse embeddings, so stub the symbol.
RUN python - <<'EOF'
import qdrant_client.qdrant_fastembed as m, os
if not hasattr(m, "IDF_EMBEDDING_MODELS"):
    with open(m.__file__, "a") as f:
        f.write("\nIDF_EMBEDDING_MODELS = []\n")
    print("Patched IDF_EMBEDDING_MODELS into", m.__file__)
EOF

ARG RERANKER_MODEL_NAME=cross-encoder/ms-marco-MiniLM-L-6-v2
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('${RERANKER_MODEL_NAME}')"

# Copy source code
COPY . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start FastAPI server
CMD ["uvicorn", "generating.app:app", "--host", "0.0.0.0", "--port", "8000"]