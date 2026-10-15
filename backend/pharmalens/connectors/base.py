"""Connector contract.

A connector fetches one source, archives the raw response under data/raw/<name>/,
normalizes it into live tables, and emits events for anything new. Every run is
recorded in connector_runs so the terminal can show feed health.
"""
import hashlib
import json
import time
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime

import httpx

from .. import db
from ..config import HTTP_TIMEOUT, RAW_DIR

BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


@dataclass
class RunStats:
    rows_seen: int = 0
    rows_new: int = 0
    events_new: int = 0
    notes: list[str] = field(default_factory=list)


class Connector:
    name: str = ""
    title: str = ""
    agency: str = ""
    # APScheduler trigger kwargs, e.g. {"trigger": "cron", "hour": 7} or {"trigger": "interval", "minutes": 15}
    schedule: dict = {"trigger": "cron", "hour": 6, "minute": 30}
    description: str = ""

    def __init__(self):
        self.stats = RunStats()
        self._http: httpx.Client | None = None

    # ---- helpers available to subclasses
    @property
    def http(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(
                timeout=HTTP_TIMEOUT, follow_redirects=True, verify=False,
                headers={"User-Agent": BROWSER_UA, "Accept-Language": "en-IN,en;q=0.9"},
            )
        return self._http

    def get(self, url: str, retries: int = 3, **kw) -> httpx.Response:
        last = None
        for i in range(retries):
            try:
                r = self.http.get(url, **kw)
                if r.status_code < 500:
                    return r
                last = RuntimeError(f"HTTP {r.status_code} for {url}")
            except httpx.HTTPError as e:
                last = e
            time.sleep(2 * (i + 1))
        raise last  # type: ignore[misc]

    def archive(self, content: bytes | str, ext: str, key: str | None = None) -> str:
        d = RAW_DIR / self.name / datetime.now().strftime("%Y-%m")
        d.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            content = content.encode("utf-8")
        key = key or hashlib.sha1(content).hexdigest()[:16]
        p = d / f"{key}.{ext}"
        if not p.exists():
            p.write_bytes(content)
        return str(p)

    def emit(self, cur, *, kind: str, title: str, severity: str = "info", ts=None, body: str | None = None,
             url: str | None = None, entity_type: str | None = None, entity_id: int | None = None,
             dedupe_key: str, payload: dict | None = None) -> bool:
        """Insert an event once (dedupe_key is unique). Returns True if new."""
        before = cur.execute("SELECT count(*) FROM events WHERE dedupe_key = ?", [dedupe_key]).fetchone()[0]
        if before:
            return False
        if isinstance(ts, date) and not isinstance(ts, datetime):
            ts = datetime.combine(ts, datetime.min.time())
        cur.execute(
            """INSERT INTO events (ts, detected_at, kind, severity, title, body, source, url, entity_type, entity_id, dedupe_key, payload)
               VALUES (?, now(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [ts or datetime.now(), kind, severity, title[:500], body, self.title or self.name, url,
             entity_type, entity_id, dedupe_key, json.dumps(payload, default=str) if payload else None],
        )
        self.stats.events_new += 1
        return True

    # ---- to implement
    def run(self):
        raise NotImplementedError

    def close(self):
        if self._http is not None:
            self._http.close()


def execute(conn_cls: type[Connector]) -> dict:
    """Run one connector and record the outcome in connector_runs."""
    c = conn_cls()
    started = datetime.now()
    status, message = "ok", None
    try:
        c.run()
        if c.stats.notes:
            message = "; ".join(c.stats.notes)[:1000]
    except Exception as e:  # noqa: BLE001 — a failing source must not take down the scheduler
        status = "error"
        message = f"{type(e).__name__}: {e}"[:1000]
        traceback.print_exc()
    finally:
        c.close()
    finished = datetime.now()
    with db.writer() as cur:
        cur.execute(
            """INSERT INTO connector_runs (connector, started_at, finished_at, status, rows_seen, rows_new, events_new, message)
               VALUES (?,?,?,?,?,?,?,?)""",
            [c.name, started, finished, status, c.stats.rows_seen, c.stats.rows_new, c.stats.events_new, message],
        )
    return {
        "connector": c.name, "status": status, "seconds": round((finished - started).total_seconds(), 1),
        "rows_seen": c.stats.rows_seen, "rows_new": c.stats.rows_new, "events_new": c.stats.events_new,
        "message": message,
    }
