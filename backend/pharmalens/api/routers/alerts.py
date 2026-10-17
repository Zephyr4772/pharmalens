"""Alert subscriptions, channels and the in-app inbox."""
import json
import os

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ... import alerts, db, scheduler
from ..common import cleanrows

router = APIRouter(prefix="/alerts", tags=["alerts"])

KINDS = ["ban", "nsq", "spurious", "recall", "price_notification", "approval", "launch", "trial", "gazette", "news", "stock"]


class Channel(BaseModel):
    type: str = Field(pattern="^(telegram|email|webhook)$")
    chat_id: str | None = None
    to: str | None = None
    url: str | None = None


class Subscription(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    channels: list[Channel] = []
    kinds: list[str] = []
    min_severity: str = Field("info", pattern="^(info|medium|high|critical)$")
    watch: list[dict] = []
    shelf_csv: str | None = None
    digest_hour: int | None = Field(None, ge=0, le=23)
    instant: bool = True
    active: bool = True


def _validate(s: Subscription):
    for ch in s.channels:
        if ch.type == "telegram" and not (ch.chat_id or "").lstrip("-").isdigit():
            raise HTTPException(400, "telegram channel needs a numeric chat_id")
        if ch.type == "email" and "@" not in (ch.to or ""):
            raise HTTPException(400, "email channel needs a valid address")
        if ch.type == "webhook" and not (ch.url or "").startswith("https://"):
            raise HTTPException(400, "webhook url must be https")
    bad = [k for k in s.kinds if k not in KINDS]
    if bad:
        raise HTTPException(400, f"unknown kinds: {bad}")


def _row(r: dict) -> dict:
    for k in ("channels", "watch"):
        if isinstance(r.get(k), str):
            r[k] = json.loads(r[k])
    r["kinds"] = [k for k in (r.get("kinds") or "").split(",") if k]
    r["shelf_items"] = len([l for l in (r.get("shelf_csv") or "").splitlines()[1:] if l.strip()])
    r.pop("shelf_state", None)
    return r


@router.get("/meta")
def meta():
    return {"channels": alerts.channel_status(), "kinds": KINDS, "public_url": alerts.PUBLIC_URL}


@router.get("/subscriptions")
def list_subs():
    cur = db.cursor()
    rows = db.rows(cur, """SELECT s.*, (SELECT count(*) FROM alert_messages m WHERE m.sub_id = s.id) AS messages,
                                  (SELECT max(created_at) FROM alert_messages m WHERE m.sub_id = s.id) AS last_message
                           FROM alert_subscriptions s ORDER BY s.id""")
    return {"data": cleanrows([_row(r) for r in rows])}


@router.post("/subscriptions")
def create_sub(s: Subscription):
    _validate(s)
    cur = db.cursor()
    max_eid = cur.execute("SELECT coalesce(max(id), 0) FROM events").fetchone()[0]
    max_nsq = cur.execute("SELECT coalesce(max(id), 0) FROM reg_nsq").fetchone()[0]
    with db.writer() as w:
        w.execute("""INSERT INTO alert_subscriptions (name, channels, kinds, min_severity, watch, shelf_csv, digest_hour, instant, active,
                     last_event_id, last_nsq_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?, now())""",
                  [s.name, json.dumps([c.model_dump(exclude_none=True) for c in s.channels]), ",".join(s.kinds) or None,
                   s.min_severity, json.dumps(s.watch), s.shelf_csv, s.digest_hour, s.instant, s.active, max_eid, max_nsq])
        sid = w.execute("SELECT max(id) FROM alert_subscriptions").fetchone()[0]
    return {"id": sid}


@router.put("/subscriptions/{sid}")
def update_sub(sid: int, s: Subscription):
    _validate(s)
    with db.writer() as w:
        if not w.execute("SELECT 1 FROM alert_subscriptions WHERE id = ?", [sid]).fetchone():
            raise HTTPException(404, "not found")
        w.execute("""UPDATE alert_subscriptions SET name = ?, channels = ?, kinds = ?, min_severity = ?, watch = ?,
                     shelf_csv = ?, digest_hour = ?, instant = ?, active = ?,
                     shelf_state = CASE WHEN shelf_csv IS DISTINCT FROM ? THEN NULL ELSE shelf_state END WHERE id = ?""",
                  [s.name, json.dumps([c.model_dump(exclude_none=True) for c in s.channels]), ",".join(s.kinds) or None,
                   s.min_severity, json.dumps(s.watch), s.shelf_csv, s.digest_hour, s.instant, s.active, s.shelf_csv, sid])
    return {"id": sid}


@router.delete("/subscriptions/{sid}")
def delete_sub(sid: int):
    with db.writer() as w:
        w.execute("DELETE FROM alert_messages WHERE sub_id = ?", [sid])
        w.execute("DELETE FROM alert_subscriptions WHERE id = ?", [sid])
    return {"deleted": sid}


@router.post("/subscriptions/{sid}/test")
async def test_sub(sid: int):
    try:
        return await run_in_threadpool(alerts.send_test, sid)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/dispatch")
async def dispatch_now():
    return await run_in_threadpool(scheduler.run_now, "alerts_dispatch")


@router.get("/inbox")
def inbox(sub_id: int | None = None, unread: bool = False, limit: int = 100):
    where, args = ["1=1"], []
    if sub_id:
        where.append("m.sub_id = ?"); args.append(sub_id)
    if unread:
        where.append("m.read_at IS NULL")
    cur = db.cursor()
    rows = db.rows(cur, f"""SELECT m.*, s.name AS subscription FROM alert_messages m LEFT JOIN alert_subscriptions s ON s.id = m.sub_id
                            WHERE {' AND '.join(where)} ORDER BY m.id DESC LIMIT ?""", args + [min(limit, 500)])
    for r in rows:
        if isinstance(r.get("deliveries"), str):
            r["deliveries"] = json.loads(r["deliveries"])
    unread_n = cur.execute("SELECT count(*) FROM alert_messages WHERE read_at IS NULL AND kind <> 'test'").fetchone()[0]
    return {"data": cleanrows(rows), "unread": unread_n}


@router.post("/inbox/read")
def mark_read(ids: list[int] | None = None):
    with db.writer() as w:
        if ids:
            w.execute(f"UPDATE alert_messages SET read_at = now() WHERE id IN ({','.join('?' * len(ids))})", ids)
        else:
            w.execute("UPDATE alert_messages SET read_at = now() WHERE read_at IS NULL")
    return {"ok": True}


@router.get("/telegram/chats")
def telegram_chats():
    """After you send any message to your bot, this lists the chat ids it can reach."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise HTTPException(400, "TELEGRAM_BOT_TOKEN not set in .env")
    r = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
    chats = {}
    for u in r.json().get("result", []):
        msg = u.get("message") or u.get("channel_post") or {}
        ch = msg.get("chat") or {}
        if ch.get("id"):
            chats[ch["id"]] = ch.get("title") or " ".join(x for x in (ch.get("first_name"), ch.get("last_name")) if x) or ch.get("username")
    return {"data": [{"chat_id": k, "name": v} for k, v in chats.items()]}
