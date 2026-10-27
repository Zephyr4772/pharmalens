# PharmaLens server image: API + scheduler (connectors) + built web UI.
# Build context is the repo root; the web UI must be built first (npm --prefix web run build).
FROM python:3.12-slim

# timestamps in the database are naive local time (IST), as on the original laptop install
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
ENV TZ=Asia/Kolkata PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 PIP_NO_CACHE_DIR=1 \
    PHARMALENS_DB=/app/data/pharmalens.duckdb \
    PHARMALENS_DUCKDB_TEMP=/app/data/duckdb_tmp

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/ backend/
COPY web/dist/ web/dist/
# project docs: the operator bot reads them to answer questions about scope, sources and decisions
COPY docs/ docs/
COPY README.md HANDOFF.md ./

EXPOSE 8010
CMD ["python", "-W", "ignore", "-m", "uvicorn", "pharmalens.api.main:app", "--host", "0.0.0.0", "--port", "8010", "--app-dir", "backend"]
