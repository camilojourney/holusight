FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

# CPU-only torch keeps the image buildable on space-constrained hosts (no CUDA wheels)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -e ".[server]"

RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

ENV CODESIGHT_DATA_DIR=/index
ENV CODESIGHT_DOCUMENTS_DIR=/data
ENV CODESIGHT_PRODUCTION=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "codesight.web.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
