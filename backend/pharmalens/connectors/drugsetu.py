"""DrugSetu developer API (api.drugsetu.com).

The product list is ordered newest-first, so each run walks pages from the top until it
reaches products already seen: that is the new-launch feed. Product pages also enrich
on demand (live MRP per pack + safety profile) through `lookup()`.

The key's plan caps page size (5 on trial), rate (~1 req/s) and monthly quota, so every
call goes through one throttled client and the scan stops early on 429/403.
"""
import gzip
import json
import re
import threading
import time
from datetime import datetime, timedelta

import httpx

from .. import db, matcher
from ..config import DATA_DIR, DRUGSETU_API_KEY
from ..normalize import norm
from .base import Connector

BASE = "https://api.drugsetu.com"
SAFETY_KEYS = ("alcohol_interaction", "pregnancy", "breastfeeding", "driving", "kidney", "liver")
PLACEHOLDER = re.compile(r"\blorem", re.I)   # vendor test rows ("Loremdolo", "Loremchem")

_lock = threading.Lock()
_last_call = 0.0
_page_size = 5


class QuotaExhausted(RuntimeError):
    pass


def call(path: str, **params) -> dict | list | None:
    """Throttled GET. Returns None on 404; raises QuotaExhausted on 403/429-after-retry."""
    global _last_call, _page_size
    if not DRUGSETU_API_KEY:
        raise QuotaExhausted("DRUGSETU_API_KEY not set")
    with _lock:
        for attempt in range(3):
            wait = 1.2 - (time.time() - _last_call)
            if wait > 0:
                time.sleep(wait)
            _last_call = time.time()
            r = httpx.get(BASE + path, params=params, headers={"X-API-Key": DRUGSETU_API_KEY}, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
            if r.status_code == 429:
                body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                if "trial" in str(body.get("message", "")).lower():
                    raise QuotaExhausted(body.get("message"))
                time.sleep(float(body.get("retryAfter", 2)) + attempt)
                continue
            if r.status_code == 400 and "page size" in r.text and "limit" in params:
                m = re.search(r"maximum of (\d+)", r.text)
                if m:
                    _page_size = int(m.group(1))
                    params["limit"] = _page_size
                    continue
            if r.status_code in (401, 403):
                raise QuotaExhausted(f"{r.status_code}: {r.text[:160]}")
            r.raise_for_status()
        raise QuotaExhausted("rate limited")


def upsert(cur, p: dict) -> tuple[bool, int | None]:
    """Store one DrugSetu product; returns (is_new, matched catalog product id)."""
    pack = (p.get("packagings") or [{}])[0] or {}
    name = p.get("product_name") or ""
    nn = norm(name)
    match = cur.execute("SELECT id FROM products WHERE name_norm = ? ORDER BY source_count DESC LIMIT 1", [nn]).fetchone()
    pid = match[0] if match else None
    exists = cur.execute("SELECT 1 FROM drugsetu_products WHERE product_id = ?", [p["product_id"]]).fetchone()
    safety = {k: p.get(k) for k in SAFETY_KEYS if p.get(k)}
    cur.execute(
        """INSERT OR REPLACE INTO drugsetu_products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
               coalesce((SELECT first_seen FROM drugsetu_products WHERE product_id = ?), now()), now())""",
        [p["product_id"], name, nn, p.get("product_type"), p.get("composition"), p.get("marketing_company"),
         p.get("manufacturing_company"), pack.get("mrp"), pack.get("packaging"), pack.get("product_form"),
         p.get("therapeutic_class"), p.get("action_class"), p.get("chemical_class"), p.get("habit_forming"),
         json.dumps(safety) if safety else None, json.dumps(p, ensure_ascii=False), pid, p["product_id"]],
    )
    if pid and pack.get("mrp"):
        cur.execute("INSERT OR IGNORE INTO price_observations VALUES (?, current_date, ?, 'drugsetu')", [pid, pack["mrp"]])
    return (not exists), pid


def lookup(product_id: int) -> dict | None:
    """Live enrichment for one catalog product (cached 14 days)."""
    cur = db.cursor()
    row = db.one(cur, """SELECT * FROM drugsetu_products WHERE catalog_product_id = ?
                         AND fetched_at > now() - INTERVAL 14 DAY ORDER BY fetched_at DESC LIMIT 1""", [product_id])
    if row:
        return row
    p = db.one(cur, "SELECT name, name_norm FROM products WHERE id = ?", [product_id])
    if not p:
        return None
    # last saved copy, however old — used whenever the API is unavailable (trial over, quota, outage)
    cached = db.one(cur, """SELECT * FROM drugsetu_products WHERE catalog_product_id = ? OR name_norm = ?
                            ORDER BY fetched_at DESC LIMIT 1""", [product_id, p["name_norm"]])
    if api_paused():
        return {**cached, "stale": True} if cached else None
    try:
        hits = call("/v1/products/search", q=p["name"][:100], type="drug") or []
        hit = next((h for h in hits if norm(h["product_name"]) == p["name_norm"]), None)
        detail = call(f"/v1/products/{hit['product_id']}") if hit else None
    except QuotaExhausted as e:
        pause_api(str(e))
        detail = None
    except httpx.HTTPError:
        detail = None
    if not detail:
        return {**cached, "stale": True} if cached else None
    with db.writer() as w:
        upsert(w, detail)
        archive_records([detail])
    return db.one(db.cursor(), "SELECT * FROM drugsetu_products WHERE product_id = ?", [detail["product_id"]])


# ------------------------------------------------------------------ durable archive + quota pause
ARCHIVE_DIR = DATA_DIR / "sources" / "drugsetu"


def archive_records(records: list[dict]) -> None:
    """Append raw API records to a dated gzip JSONL file: an API-independent copy of everything fetched."""
    if not records:
        return
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = ARCHIVE_DIR / f"products-{datetime.now():%Y%m%d}.jsonl.gz"
    with gzip.open(path, "at", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _state(key: str) -> str | None:
    r = db.cursor().execute("SELECT value FROM drugsetu_state WHERE key = ?", [key]).fetchone()
    return r[0] if r else None


def _set_state(key: str, value: str | None) -> None:
    with db.writer() as w:
        if value is None:
            w.execute("DELETE FROM drugsetu_state WHERE key = ?", [key])
        else:
            w.execute("INSERT OR REPLACE INTO drugsetu_state VALUES (?, ?)", [key, value])


def pause_api(reason: str, hours: int = 6) -> None:
    """After a quota/auth refusal, stop calling the API for a while instead of hammering it."""
    _set_state("paused_until", (datetime.now() + timedelta(hours=hours)).isoformat())
    _set_state("paused_reason", reason[:300])


def api_paused() -> bool:
    if not DRUGSETU_API_KEY:
        return True
    until = _state("paused_until")
    return bool(until and datetime.fromisoformat(until) > datetime.now())


class DrugSetuHarvest(Connector):
    """Pulls DrugSetu's whole approved catalog, page by page, resuming where it stopped.
    Everything lands in drugsetu_products and in data/sources/drugsetu/*.jsonl.gz, so the data
    stays usable after the API key lapses."""
    name = "drugsetu_harvest"
    title = "DrugSetu Catalog Harvest"
    agency = "DrugSetu API"
    schedule = {"trigger": "interval", "minutes": 30}
    description = "Resumable full-catalog copy of DrugSetu (all product fields) into the local database and gzip JSONL archive."
    max_pages_per_run = 1400   # ~28 min at the trial rate limit; the next run continues from the saved cursor

    def run(self):
        if _state("harvest_done"):
            self.stats.notes.append(f"complete since {_state('harvest_done')}")
            return
        if api_paused():
            self.stats.notes.append(f"API paused: {_state('paused_reason') or 'no key'}")
            return
        cursor = _state("harvest_cursor")
        pages = 0
        try:
            while pages < self.max_pages_per_run:
                # medicines only: the quota is too scarce to spend on supplements and cosmetics
                params = {"limit": _page_size, "type": "drug"}
                if cursor:
                    params["cursor"] = cursor
                page = call("/v1/products", **params)
                pages += 1
                data = (page or {}).get("data") or []
                if data:
                    with db.writer() as w:
                        for p in data:
                            self.stats.rows_seen += 1
                            if PLACEHOLDER.search(f"{p.get('product_name')} {p.get('marketing_company')}"):
                                continue
                            is_new, _ = upsert(w, p)
                            self.stats.rows_new += int(is_new)
                    archive_records(data)
                if not page or not page.get("has_next"):
                    _set_state("harvest_done", datetime.now().isoformat())
                    _set_state("harvest_cursor", None)
                    break
                cursor = page.get("next_cursor")
                if pages % 20 == 0:
                    _set_state("harvest_cursor", cursor)   # checkpoint
        except QuotaExhausted as e:
            pause_api(str(e))
            self.stats.notes.append(f"stopped: {e}")
        finally:
            if cursor and not _state("harvest_done"):
                _set_state("harvest_cursor", cursor)
        total = db.cursor().execute("SELECT count(*) FROM drugsetu_products").fetchone()[0]
        self.stats.notes.append(f"{pages} pages this run · {total:,} products stored")


class DrugSetuLaunches(Connector):
    name = "drugsetu_launches"
    title = "DrugSetu New Product Listings"
    agency = "DrugSetu API"
    schedule = {"trigger": "cron", "hour": "*/6", "minute": 35}
    description = ("Walks DrugSetu's newest-first approved product list until it reaches known products; "
                   "new SKUs become launch events with live MRP and safety profile.")
    max_pages = 40  # quota guard: ~200 products per run on the trial page size

    def run(self):
        if api_paused():
            self.stats.notes.append(f"API paused: {_state('paused_reason') or 'no key'}")
            return
        cur = db.cursor()
        first_run = cur.execute("SELECT count(*) FROM drugsetu_products").fetchone()[0] == 0
        cursor, pages, known_streak = None, 0, 0
        try:
            while pages < self.max_pages:
                params = {"limit": _page_size, "type": "drug"}
                if cursor:
                    params["cursor"] = cursor
                page = call("/v1/products", **params)
                pages += 1
                if not page or not page.get("data"):
                    break
                archive_records(page["data"])
                with db.writer() as w:
                    for p in page["data"]:
                        self.stats.rows_seen += 1
                        if PLACEHOLDER.search(f"{p.get('product_name')} {p.get('marketing_company')}"):
                            continue
                        is_new, pid = upsert(w, p)
                        if not is_new:
                            known_streak += 1
                            continue
                        known_streak = 0
                        self.stats.rows_new += 1
                        if first_run:
                            continue
                        pack = (p.get("packagings") or [{}])[0] or {}
                        mids = matcher.molecules_in(p.get("composition") or "", limit=6)
                        cid = matcher.company_for(p.get("marketing_company"))
                        self.emit(w, kind="launch", severity="info",
                                  title=f"New listing: {p['product_name']} — {p.get('marketing_company')}"
                                        + (f" · ₹{pack['mrp']}" if pack.get("mrp") else "")
                                        + ("" if pid else " (not in catalog)"),
                                  body=p.get("composition"), entity_type="company" if cid else None, entity_id=cid,
                                  dedupe_key=f"ds|{p['product_id']}",
                                  payload={"composition": p.get("composition"), "molecule_ids": mids, "catalog_product_id": pid})
                if known_streak >= 15 or not page.get("has_next"):
                    break
                cursor = page.get("next_cursor")
        except QuotaExhausted as e:
            pause_api(str(e))
            self.stats.notes.append(f"stopped: {e}")
        self.stats.notes.append(f"{pages} pages")
        with db.writer() as w:
            w.execute("INSERT OR REPLACE INTO drugsetu_state VALUES ('last_scan', ?)", [datetime.now().isoformat()])
