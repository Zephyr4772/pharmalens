"""The watchlist: what a user follows (groups, companies, molecules, combinations, SKUs), kept on the server.

One list per user, keyed by Tailscale login, shared by the terminal's stars, Specs' /watch commands and the alert
engine: the owner's list is mirrored into a system subscription ("Specs: watchlist") that sends matching events
(and NSQ batches for watched makers or molecules) to the owner's Telegram chat.
"""
import json
import os

from . import db

SYSTEM_SUB = "Specs: watchlist"
SKIP_KINDS = {"news"}          # news about watched names arrives in briefings, not as instant pings


def owner_login() -> str:
    """The owner's key: the first login in PHARMALENS_OWNERS (server), 'local' in development."""
    owners = [o.strip().lower() for o in os.getenv("PHARMALENS_OWNERS", "").split(",") if o.strip()]
    return owners[0] if owners else "local"


def items(owner: str) -> list[dict]:
    return db.rows(db.cursor(), "SELECT key, label, href, added_at FROM watchlist WHERE owner = ? ORDER BY added_at", [owner])


def add(owner: str, key: str, label: str, href: str | None = None) -> bool:
    """True if newly added."""
    with db.writer() as w:
        if w.execute("SELECT 1 FROM watchlist WHERE owner = ? AND key = ?", [owner, key]).fetchone():
            return False
        w.execute("INSERT INTO watchlist VALUES (?, ?, ?, ?, now())", [owner, key, label, href])
    if owner == owner_login():
        sync_subscription()
    return True


def remove(owner: str, key: str) -> bool:
    with db.writer() as w:
        found = w.execute("SELECT 1 FROM watchlist WHERE owner = ? AND key = ?", [owner, key]).fetchone()
        w.execute("DELETE FROM watchlist WHERE owner = ? AND key = ?", [owner, key])
    if found and owner == owner_login():
        sync_subscription()
    return bool(found)


def sync_subscription() -> None:
    """Keep the system subscription's watch list equal to the owner's watchlist (created on first use)."""
    chat = os.getenv("HEALTH_TELEGRAM_CHAT")
    if not chat:
        return
    watch = [{"key": i["key"], "label": i["label"]} for i in items(owner_login())]
    kinds = ",".join(sorted({"nsq", "spurious", "ban", "price_notification", "approval", "recall", "launch", "usfda", "stock",
                             "shortage", "gazette", "tender", "filing", "results", "results_due", "trial"} - SKIP_KINDS))
    with db.writer() as w:
        row = w.execute("SELECT id FROM alert_subscriptions WHERE name = ?", [SYSTEM_SUB]).fetchone()
        if row:
            w.execute("UPDATE alert_subscriptions SET watch = ?, channels = ?, active = ? WHERE id = ?",
                      [json.dumps(watch), json.dumps([{"type": "telegram", "chat_id": chat}]), bool(watch), row[0]])
        elif watch:
            max_eid = w.execute("SELECT coalesce(max(id), 0) FROM events").fetchone()[0]
            max_nsq = w.execute("SELECT coalesce(max(id), 0) FROM reg_nsq").fetchone()[0]
            w.execute("""INSERT INTO alert_subscriptions (name, channels, kinds, min_severity, watch, digest_hour, instant, active,
                         last_event_id, last_nsq_id, created_at) VALUES (?, ?, ?, 'info', ?, NULL, TRUE, TRUE, ?, ?, now())""",
                      [SYSTEM_SUB, json.dumps([{"type": "telegram", "chat_id": chat}]), kinds, json.dumps(watch), max_eid, max_nsq])
