"""Operational health alerts to Telegram (HEALTH_TELEGRAM_CHAT in .env).

Checked every 15 minutes inside the server; each problem is announced once when it starts and once when it clears:
* a feed that failed on its last two runs;
* a feed that has not succeeded for much longer than its schedule implies;
* the home-relay copy of a source that blocks the server is close to expiring;
* low disk on the server, or no nightly backup in the last 30 hours.
A server that is down cannot report itself.
"""
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from .. import db
from ..alerts import send_telegram
from ..config import DATA_DIR, RAW_DIR
from .base import Connector

STATE = "health2|"      # problems already announced (key -> message)
BACKUP_MARK = Path(os.getenv("PHARMALENS_BACKUP_MARK", "/srv/backups/last_run.txt"))


def expected_gap(schedule: dict) -> timedelta:
    """How long a healthy feed can go between successful runs, from its APScheduler trigger."""
    if schedule.get("trigger") == "interval":
        mins = schedule.get("minutes", 0) + 60 * schedule.get("hours", 0) + 1440 * schedule.get("days", 0)
        return timedelta(minutes=max(mins * 4, 180))
    if "day" in schedule:                       # monthly
        return timedelta(days=35)
    if "day_of_week" in schedule:
        n = len(str(schedule["day_of_week"]).split(","))
        return timedelta(days=8 if n == 1 else 4 if n == 2 else 2)
    return timedelta(hours=40)                  # daily (one or more hours)


class HealthWatch(Connector):
    name = "health_watch"
    title = "Operational health alerts"
    agency = "PharmaLens"
    schedule = {"trigger": "interval", "minutes": 15}
    description = "Telegram alerts when feeds fail or go stale, the relay copy expires, disk is low or backups stop."

    def problems(self) -> dict[str, str]:
        from . import REGISTRY
        cur = db.cursor()
        found = {}
        runs = {}
        for name, status, finished, msg in cur.execute("""
                SELECT connector, status, finished_at, message FROM (
                  SELECT *, row_number() OVER (PARTITION BY connector ORDER BY started_at DESC) rn FROM connector_runs) WHERE rn <= 2
                ORDER BY connector, finished_at DESC""").fetchall():
            runs.setdefault(name, []).append((status, finished, msg))
        last_ok = dict(cur.execute("SELECT connector, max(finished_at) FROM connector_runs WHERE status = 'ok' GROUP BY 1").fetchall())
        now = datetime.now()
        for name, cls in REGISTRY.items():
            if name in ("health_watch", "drugsetu_harvest", "drugsetu_launches"):   # DrugSetu is knowingly paused
                continue
            r = runs.get(name, [])
            if len(r) >= 2 and all(s == "error" for s, _, _ in r):
                found[f"feed-failing|{name}"] = f"{cls.title} failed on its last two runs: {(r[0][2] or '')[:200]}"
            ok = last_ok.get(name)
            if ok and now - ok > expected_gap(cls.schedule):
                found[f"feed-stale|{name}"] = f"{cls.title} has not succeeded since {ok:%d %b %H:%M} (expected every ~{expected_gap(cls.schedule)})"
            if getattr(cls, "relay_url", None):
                f = RAW_DIR / "relay" / f"{name}.html"
                age = (time.time() - f.stat().st_mtime) / 86400 if f.exists() else None
                if age is None or age > cls.relay_max_age_days - 2:
                    found[f"relay-stale|{name}"] = (f"{cls.title}: the laptop relay copy is {age:.0f} days old (expires at {cls.relay_max_age_days}); "
                                                     "is the 'PharmaLens relay' task running?") if age is not None else f"{cls.title}: no relay copy uploaded yet"
        du = shutil.disk_usage(DATA_DIR)
        if du.free / du.total < 0.12:
            found["disk"] = f"Server disk {du.free / 2**30:.1f} GB free of {du.total / 2**30:.0f} GB"
        if BACKUP_MARK.exists() and time.time() - BACKUP_MARK.stat().st_mtime > 30 * 3600:
            found["backup"] = f"No nightly backup since {datetime.fromtimestamp(BACKUP_MARK.stat().st_mtime):%d %b %H:%M}"
        return found

    def run(self):
        chat = os.getenv("HEALTH_TELEGRAM_CHAT")
        found = self.problems()
        cur = db.cursor()
        open_keys = {r[0][len(STATE):]: r[1] for r in cur.execute("SELECT key, value FROM connector_state WHERE starts_with(key, ?)", [STATE]).fetchall()}
        new = {k: v for k, v in found.items() if k not in open_keys}
        cleared = [k for k in open_keys if k not in found]
        self.stats.rows_seen = len(found)
        if not chat:
            # nothing can be announced yet: keep no state, so every open problem is sent once a chat is configured
            self.stats.notes.append("HEALTH_TELEGRAM_CHAT not set; open: " + " | ".join(found)[:900])
            return
        sent = 0
        if chat and (new or cleared):
            lines = [f"⚠ {v}" for v in new.values()] + [f"✅ resolved: {open_keys[k][:160]}" for k in cleared]
            try:
                send_telegram(chat, "PharmaLens health", "\n".join(lines), None)
                sent = len(lines)
            except Exception as e:  # noqa: BLE001 — keep state unchanged so the alert is retried next run
                self.stats.notes.append(f"telegram failed: {e}")
                return
        with db.writer() as w:
            for k, v in new.items():
                w.execute("INSERT OR REPLACE INTO connector_state VALUES (?, ?)", [f"{STATE}{k}", v])
            for k in cleared:
                w.execute("DELETE FROM connector_state WHERE key = ?", [f"{STATE}{k}"])
            w.execute("DELETE FROM connector_state WHERE key LIKE 'health|%'")   # state written by the first build, never announced
        self.stats.rows_new = len(new)
        self.stats.notes.append(f"{len(found)} open problems ({len(new)} new, {len(cleared)} cleared); {sent} lines sent"
                                + ("" if chat else "; HEALTH_TELEGRAM_CHAT not set"))
