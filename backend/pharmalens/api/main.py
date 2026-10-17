"""PharmaLens Terminal API.

    cd backend && py -3 -m uvicorn pharmalens.api.main:app --port 8010

Owns the DuckDB file and runs the connector scheduler in-process.
Set PHARMALENS_SCHEDULER=0 to serve without background refreshes.
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .. import db, scheduler
from ..config import WEB_DIST
from .routers import alerts, catalog, live, market, pipeline, regulatory, shelf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.get_conn()
    from ..derived import migrate
    migrate()
    if os.getenv("PHARMALENS_SCHEDULER", "1") != "0":
        scheduler.start()
    yield
    scheduler.shutdown()
    db.close()


app = FastAPI(title="PharmaLens Terminal API", version="4.0", lifespan=lifespan,
              description="Real-time intelligence on the Indian pharmaceutical market.")
app.add_middleware(GZipMiddleware, minimum_size=2048)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(db.DatabaseUnavailable)
def db_unavailable(request: Request, exc: db.DatabaseUnavailable):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


for r in (catalog, market, regulatory, pipeline, live, shelf, alerts):
    app.include_router(r.router, prefix="/api/v1")


if WEB_DIST.exists():
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "not found"})
        candidate = (WEB_DIST / full_path).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(WEB_DIST.resolve())):
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")
