"""Live layer: event tape, SSE stream, news, quotes, feed health, connector control."""
import asyncio
import json
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from ... import db, scheduler
from ...config import SCHEMA_VERSION
from ...connectors import REGISTRY
from ..common import cleanrows, paged

router = APIRouter(tags=["live"])


@router.get("/healthz")
def healthz():
    t0 = time.perf_counter()
    db.cursor().execute("SELECT 1").fetchone()
    return {"ok": True, "probe_ms": round((time.perf_counter() - t0) * 1000, 2), "schema": SCHEMA_VERSION}


@router.get("/meta/build")
def build():
    return dict(db.cursor().execute("SELECT key, value FROM build_meta").fetchall())


# The "How it works" page: what the feeds have collected, how reliably they run, and how the jobs are grouped.
AREAS = {
    "Indian regulators": ["cdsco_nsq_portal", "cdsco_nsq", "nsq_mirror", "banned_fdc", "cdsco_gazette", "cdsco_alerts", "cdsco_approvals",
                          "cdsco_approvals_db", "cdsco_sec", "cdsco_brands", "pvpi_alerts", "nlem", "cdci"],
    "Prices": ["nppa_orders", "nppa_retail_prices", "nppa_compendium", "nppa_history", "mfr_price_lists", "jan_aushadhi"],
    "State procurement": ["rmscl_rates", "tnmsc_rates", "hmscl_rates", "upmscl_debarments"],
    "Markets": ["nse_quotes", "nse_filings", "nse_results", "nse_fundamentals", "nse_history"],
    "News": ["pharma_news", "news_archive"],
    "US and global": ["fda_inspections", "fda_compliance", "fda_ia_6640", "openfda_recalls", "openfda_bulk", "ctgov_india", "who_pq",
                      "ema_medicines", "who_alerts", "molecule_enrichment"],
    "Internal jobs": ["entity_linker", "name_index", "parent_sync", "alerts_dispatch", "health_watch", "bot_briefing", "results_preview",
                      "results_summary", "weekly_digest"],
}
SHOW_COUNTS = ["products", "molecules", "combos", "companies", "parents", "makers", "sites", "entity_links", "reg_nsq", "reg_approvals",
               "reg_banned_fdc", "sec_items", "brand_registry", "cdci_brand", "price_observations", "mfr_prices", "nppa_retail_prices",
               "nppa_ceiling", "procurement_rates", "fda_inspections", "fda_citations", "fda_compliance_actions", "fda_import_refusals",
               "usfda_actions", "us_applications", "us_orange_book", "us_ndc", "us_patents", "ema_medicines", "who_pq", "trials",
               "quote_history", "corp_announcements", "fin_results", "news", "events"]
SHOW_RANGES = {"reg_nsq": "alert_month", "reg_approvals": "approved_on", "price_observations": "observed_on", "fda_inspections": "end_date",
               "fda_compliance_actions": "action_date", "fda_import_refusals": "refusal_date", "quote_history": "d", "news": "published_at",
               "corp_announcements": "announced_at", "nppa_retail_prices": "notified_on"}
_showcase: dict[str, tuple[float, dict]] = {}


@router.get("/meta/showcase")
def showcase():
    hit = _showcase.get("v")
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    from collections import Counter

    from ... import licensing
    cur = db.cursor()
    counts, ranges = {}, {}
    for t in SHOW_COUNTS:
        try:
            counts[t] = cur.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        except Exception:  # noqa: BLE001 — a feed not loaded yet
            counts[t] = None
    for t, col in SHOW_RANGES.items():
        try:
            ranges[t] = [str(v)[:10] if v is not None else None for v in cur.execute(f"SELECT min({col}), max({col}) FROM {t}").fetchone()]
        except Exception:  # noqa: BLE001
            pass
    runs = {c: {"runs": n, "ok": ok} for c, n, ok in cur.execute(
        "SELECT connector, count(*), count(*) FILTER (WHERE status = 'ok') FROM connector_runs WHERE started_at > now() - INTERVAL 14 DAY GROUP BY 1").fetchall()}
    try:
        high = cur.execute("SELECT count(*) FROM entity_links WHERE confidence >= 0.85").fetchone()[0]
    except Exception:  # noqa: BLE001
        high = None
    out = {"counts": counts, "ranges": ranges, "runs14": runs, "areas": AREAS, "links_high": high,
           "licence_mix": dict(Counter(licensing.table_class(t) for t in licensing.TABLES)), "asof": datetime.now().isoformat(timespec="seconds")}
    _showcase["v"] = (time.time(), out)
    return out


@router.get("/meta/feeds")
def feeds():
    cur = db.cursor()
    last = {r["connector"]: r for r in db.rows(cur, """
        SELECT connector, status, started_at, finished_at, rows_seen, rows_new, events_new, message FROM (
          SELECT *, row_number() OVER (PARTITION BY connector ORDER BY started_at DESC) rn FROM connector_runs) WHERE rn = 1""")}
    last_ok = dict(cur.execute("SELECT connector, max(finished_at) FROM connector_runs WHERE status = 'ok' GROUP BY 1").fetchall())
    nxt = scheduler.jobs()
    running = scheduler.running()
    out = []
    for name, cls in REGISTRY.items():
        r = last.get(name, {})
        out.append({"name": name, "title": cls.title, "agency": cls.agency, "description": cls.description,
                    "schedule": cls.schedule, "next_run": nxt.get(name), "running": name in running,
                    "last_status": r.get("status"), "last_run": r.get("finished_at"), "last_ok": last_ok.get(name),
                    "rows_new": r.get("rows_new"), "events_new": r.get("events_new"), "message": r.get("message")})
    return {"data": cleanrows(out)}


@router.post("/admin/connectors/{name}/run")
async def run_connector(name: str):
    if name not in REGISTRY:
        raise HTTPException(404, "unknown connector")
    return await run_in_threadpool(scheduler.run_now, name)


@router.get("/admin/relay")
def relay_sources():
    """Sources the server cannot reach itself; the home relay fetches these and posts them back."""
    return {name: cls.relay_url for name, cls in REGISTRY.items() if getattr(cls, "relay_url", None)}


@router.post("/admin/relay/{name}")
async def relay_upload(name: str, request: Request):
    cls = REGISTRY.get(name)
    if not cls or not getattr(cls, "relay_url", None):
        raise HTTPException(404, "not a relayed source")
    body = await request.body()
    if len(body) < 500 or len(body) > 20_000_000:
        raise HTTPException(400, "implausible page size")
    from ...config import RAW_DIR
    d = RAW_DIR / "relay"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.html").write_bytes(body)
    return {"stored": name, "bytes": len(body)}


@router.post("/admin/maintenance/fix-text")
def fix_text():
    """One-off repair of mis-decoded regulator titles stored before fix_mojibake existed."""
    from ...normalize import fix_mojibake
    n = 0
    with db.writer() as cur:
        for table, key in (("events", "id"), ("reg_documents", "id"), ("reg_nsq", "id")):
            col = "product_text" if table == "reg_nsq" else "title"
            for rid, txt in cur.execute(f"SELECT {key}, {col} FROM {table} WHERE {col} LIKE '%Â%' OR {col} LIKE '%â%' OR {col} LIKE '%Ã%'").fetchall():
                fixed = fix_mojibake(txt)
                if fixed != txt:
                    cur.execute(f"UPDATE {table} SET {col} = ? WHERE {key} = ?", [fixed, rid])
                    n += 1
    return {"fixed": n}


@router.get("/events")
def events(kind: str | None = None, severity: str | None = None, since_id: int | None = None,
           entity_type: str | None = None, entity_id: int | None = None, q: str | None = None,
           page: int = 1, limit: int = Query(50, le=500)):
    where, args = ["1=1"], []
    if kind:
        kinds = kind.split(",")
        where.append(f"kind IN ({','.join('?' * len(kinds))})"); args += kinds
    if severity:
        sev = severity.split(",")
        where.append(f"severity IN ({','.join('?' * len(sev))})"); args += sev
    if since_id:
        where.append("id > ?"); args.append(since_id)
    if entity_type:
        where.append("entity_type = ?"); args.append(entity_type)
    if entity_id:
        where.append("entity_id = ?"); args.append(entity_id)
    if q:
        where.append("lower(title) LIKE ?"); args.append(f"%{q.lower()}%")
    w = " AND ".join(where)
    cur = db.cursor()
    total = cur.execute(f"SELECT count(*) FROM events WHERE {w}", args).fetchone()[0]
    data = db.rows(cur, f"""SELECT id, ts, detected_at, kind, severity, title, body, source, url, entity_type, entity_id
                            FROM events WHERE {w} ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?""", args + [limit, (page - 1) * limit])
    kinds = db.rows(cur, "SELECT kind, count(*) n, max(ts) latest FROM events GROUP BY 1 ORDER BY 2 DESC")
    return paged(total, page, limit, data, kinds=cleanrows(kinds))


@router.get("/stream")
async def stream(request: Request, since_id: int | None = None):
    """Server-sent events: pushes new events and quote ticks as connectors land them."""
    async def gen():
        cur = db.cursor()
        last = since_id if since_id is not None else (cur.execute("SELECT coalesce(max(id), 0) FROM events").fetchone()[0])
        last_quote = None
        yield f"event: hello\ndata: {json.dumps({'last_id': last})}\n\n"
        while not await request.is_disconnected():
            rows = await run_in_threadpool(db.rows, db.cursor(), """
                SELECT id, ts, kind, severity, title, url, source, entity_type, entity_id FROM events
                WHERE id > ? ORDER BY id LIMIT 50""", [last])
            for r in rows:
                last = r["id"]
                yield f"event: event\ndata: {json.dumps(cleanrows([r])[0], default=str)}\n\n"
            q = await run_in_threadpool(lambda: db.cursor().execute("SELECT max(quoted_at) FROM quotes").fetchone()[0])
            if q and q != last_quote:
                last_quote = q
                yield f"event: quotes\ndata: {json.dumps({'at': str(q)})}\n\n"
            yield ": ping\n\n"
            await asyncio.sleep(5)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/news")
def news(topic: str | None = None, parent_id: int | None = None, q: str | None = None,
         page: int = 1, limit: int = Query(50, le=300)):
    where, args = ["1=1"], []
    if topic:
        where.append("topic = ?"); args.append(topic)
    if parent_id:
        where.append("list_contains(string_split(parent_ids, ','), ?)"); args.append(str(parent_id))
    if q:
        where.append("lower(title) LIKE ?"); args.append(f"%{q.lower()}%")
    w = " AND ".join(where)
    cur = db.cursor()
    total = cur.execute(f"SELECT count(*) FROM news WHERE {w}", args).fetchone()[0]
    data = db.rows(cur, f"SELECT * FROM news WHERE {w} ORDER BY published_at DESC LIMIT ? OFFSET ?", args + [limit, (page - 1) * limit])
    ids = {int(x) for r in data for x in (r["parent_ids"] or "").split(",") if x}
    names = dict(cur.execute(f"SELECT id, name FROM parents WHERE id IN ({','.join(map(str, ids)) or '0'})").fetchall())
    slugs = dict(cur.execute(f"SELECT id, slug FROM parents WHERE id IN ({','.join(map(str, ids)) or '0'})").fetchall())
    for r in data:
        r["parents"] = [{"id": int(x), "name": names.get(int(x)), "slug": slugs.get(int(x))} for x in (r["parent_ids"] or "").split(",") if x]
    topics = db.rows(cur, "SELECT topic, count(*) n FROM news WHERE published_at >= now() - INTERVAL 7 DAY GROUP BY 1 ORDER BY 2 DESC")
    return paged(total, page, limit, data, topics=cleanrows(topics))


@router.get("/quotes")
def quotes():
    cur = db.cursor()
    data = db.rows(cur, """SELECT q.*, pa.slug, pa.name AS group_name, pa.ownership FROM quotes q
                           LEFT JOIN parents pa ON pa.ticker || '.NS' = q.ticker ORDER BY q.market_cap DESC NULLS LAST""")
    spark = {}
    for t, d, c in cur.execute("""SELECT ticker, d, close FROM quote_history WHERE d >= current_date - INTERVAL 35 DAY ORDER BY ticker, d""").fetchall():
        spark.setdefault(t, []).append(c)
    for r in data:
        r["spark"] = spark.get(r["ticker"], [])
    return {"data": cleanrows(data), "asof": datetime.now().isoformat(timespec="seconds")}


@router.get("/quotes/{ticker}/history")
def quote_history(ticker: str):
    cur = db.cursor()
    return {"data": cleanrows(db.rows(cur, "SELECT d, close, volume FROM quote_history WHERE ticker = ? ORDER BY d", [ticker]))}
