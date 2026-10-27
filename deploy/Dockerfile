# PharmaLens server image: API + scheduler (connectors) + built web UI.
# Build context is the repo root; the web UI must be built first (npm --prefix web run build).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 PIP_NO_CACHE_DIR=1 \
    PHARMALENS_DB=/app/data/pharmalens.duckdb \
    PHARMALENS_DUCKDB_TEMP=/app/data/duckdb_tmp

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/ backend/
COPY web/dist/ web/dist/

EXPOSE 8010
CMD ["python", "-W", "ignore", "-m", "uvicorn", "pharmalens.api.main:app", "--host", "0.0.0.0", "--port", "8010", "--app-dir", "backend"]
