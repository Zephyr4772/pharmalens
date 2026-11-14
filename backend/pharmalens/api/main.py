"""PharmaLens Terminal API.

    cd backend && py -3 -m uvicorn pharmalens.api.main:app --port 8010

Owns the DuckDB file and runs the connector scheduler in-process.
Set PHARMALENS_SCHEDULER=0 to serve without background refreshes.
"""
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from .. import db, scheduler
from ..config import WEB_DIST
from .routers import alerts, catalog, invest, live, makers, market, pipeline, regulatory, shelf, sites, watchlist

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.get_conn()
    from ..derived import migrate
    migrate()
    if os.getenv("PHARMALENS_SCHEDULER", "1") != "0":
        scheduler.start()
        from ..watchlist import sync_subscription
        sync_subscription()  # keep the owner's alert subscription in step with code changes to its event kinds
        from ..bot.telegram import start as start_bot
        start_bot()          # DrugDen operator bot (Telegram), only with the scheduler: one poller per bot token
    yield
    scheduler.shutdown()
    db.close()


app = FastAPI(title="PharmaLens Terminal API", version="4.0", lifespan=lifespan,
              description="Real-time intelligence on the Indian pharmaceutical market.")
app.add_middleware(GZipMiddleware, minimum_size=2048)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


# Owner-only endpoints. The server is reached only through `tailscale serve`, which stamps each request with the
# signed-in Tailscale user (and drops any client-sent copy of that header). Guests (people the server is shared
# with) can read everything else; no header means guest. PHARMALENS_OWNERS unset = local dev, everyone is owner,
# unless PHARMALENS_REQUIRE_OWNER=1 (the server), where a missing list locks the owner-only endpoints for everyone.
OWNERS = {o.strip().lower() for o in os.getenv("PHARMALENS_OWNERS", "").split(",") if o.strip()}
REQUIRE_OWNER = os.getenv("PHARMALENS_REQUIRE_OWNER") == "1"
OWNER_ONLY = ("/api/v1/admin/", "/api/v1/alerts/")


def is_owner(request: Request) -> bool:
    if not OWNERS:
        return not REQUIRE_OWNER
    return request.headers.get("tailscale-user-login", "").lower() in OWNERS


@app.middleware("http")
async def owner_gate(request: Request, call_next):
    if request.url.path.startswith(OWNER_ONLY) and not is_owner(request):
        return JSONResponse(status_code=403, content={"detail": "owner only"})
    return await call_next(request)


# Public view (Tailscale Funnel): visitors from outside the tailnet arrive with no identity header. They can read the
# terminal but not change anything, export data, open the API docs or page through more than the UI ever asks for,
# and each address is rate limited. Responses ask search engines not to index them.
PUBLIC_POST = ("/api/v1/shelf/check",)
PUBLIC_RPM = int(os.getenv("PHARMALENS_PUBLIC_RPM", "300"))
_hits: dict[str, deque] = defaultdict(deque)


def is_public(request: Request) -> bool:
    return REQUIRE_OWNER and not request.headers.get("tailscale-user-login")


def _deny(status: int, detail: str, **headers) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail}, headers=headers or None)


@app.middleware("http")
async def public_gate(request: Request, call_next):
    if not is_public(request):
        return await call_next(request)
    path, q = request.url.path, request.query_params
    if path in ("/docs", "/redoc", "/openapi.json") or path.startswith("/docs/"):
        return _deny(404, "not found")
    if request.method not in ("GET", "HEAD") and path not in PUBLIC_POST:
        return _deny(403, "this is a read-only public view")
    if q.get("format") == "csv":
        return _deny(403, "exports are off in the public view")
    if q.get("limit", "").isdigit() and int(q["limit"]) > 500:
        return _deny(400, "limit is capped at 500 in the public view")
    if path.startswith("/api/"):
        key = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
        now, hits = time.monotonic(), _hits[key]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= PUBLIC_RPM:
            return _deny(429, "too many requests, slow down", **{"Retry-After": "60"})
        hits.append(now)
        if len(_hits) > 5000:   # forget addresses that have gone quiet
            for k in [k for k, v in _hits.items() if not v or now - v[-1] > 60]:
                del _hits[k]
    resp = await call_next(request)
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp


@app.get("/api/v1/me", include_in_schema=False)
def me(request: Request):
    return {"login": request.headers.get("tailscale-user-login"), "name": request.headers.get("tailscale-user-name"),
            "owner": is_owner(request), "public": is_public(request)}


@app.get("/robots.txt", include_in_schema=False)
def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


@app.exception_handler(db.DatabaseUnavailable)
def db_unavailable(request: Request, exc: db.DatabaseUnavailable):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


for r in (catalog, market, regulatory, pipeline, live, shelf, alerts, watchlist, invest, makers, sites):
    app.include_router(r.router, prefix="/api/v1")


if WEB_DIST.exists():
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "not found"})
        candidate = (WEB_DIST / full_path).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(WEB_DIST.resolve())):
            # hashed bundles never change; everything else is revalidated
            immutable = full_path.startswith("assets/")
            return FileResponse(candidate, headers={"Cache-Control": "public, max-age=31536000, immutable" if immutable else "no-cache"})
        # the app shell must be revalidated, or a browser keeps running the previous build after an update
        return FileResponse(WEB_DIST / "index.html", headers={"Cache-Control": "no-cache"})
