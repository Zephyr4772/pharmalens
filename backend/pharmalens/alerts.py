"""Alerts: route new events to subscriptions (watchlists and saved shelf lists) over
Telegram, email, webhooks (Slack / Discord / Teams / generic) and the in-app inbox.

A subscription matches an event when the event is about something it watches
(group, company, molecule, combination, SKU), or — with an empty watchlist — when the
event passes its kind / severity filters. Saved shelf lists are re-checked whenever new
bans, NSQ/spurious lists, recalls or price notices arrive; only flags that were not there
before are sent.

Channel credentials live in .env:
  TELEGRAM_BOT_TOKEN                      (create a bot with @BotFather)
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
"""
import html
import json
import logging
import os
import re
import smtplib
from datetime import date, datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import httpx

from . import db
from .normalize import norm

log = logging.getLogger("pharmalens.alerts")
IST = ZoneInfo("Asia/Kolkata")
SEV_RANK = {"info": 0, "medium": 1, "high": 2, "critical": 3}
SHELF_TRIGGER_KINDS = ("ban", "nsq", "spurious", "recall", "price_notification")
MAX_INSTANT_PER_RUN = 25
PUBLIC_URL = os.getenv("PHARMALENS_PUBLIC_URL", "http://localhost:8010")


# ------------------------------------------------------------------ channels
class ChannelError(RuntimeError):
    pass


def send_telegram(chat_id: str, title: str, body: str, url: str | None) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ChannelError("TELEGRAM_BOT_TOKEN not set in .env")
    text = f"<b>{html.escape(title)}</b>"
    if body:
        text += f"\n{html.escape(body[:3000])}"
    if url:
        text += f'\n<a href="{html.escape(url)}">open</a>'
    r = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                   json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=20)
    if r.status_code != 200:
        raise ChannelError(f"telegram {r.status_code}: {r.text[:160]}")


def send_email(to: str, title: str, body: str, url: str | None) -> None:
    host = os.getenv("SMTP_HOST")
    if not host:
        raise ChannelError("SMTP_HOST not set in .env")
    msg = EmailMessage()
    msg["Subject"] = f"[PharmaLens] {title}"[:200]
    msg["From"] = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER", "pharmalens@localhost")
    msg["To"] = to
    msg.set_content(f"{title}\n\n{body or ''}\n\n{url or ''}\n\n— PharmaLens Terminal")
    port = int(os.getenv("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=30) as s:
        if port != 25:
            s.starttls()
        if os.getenv("SMTP_USER"):
            s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
        s.send_message(msg)


def send_webhook(url: str, title: str, body: str, link: str | None, payload: dict) -> None:
    text = f"*{title}*\n{body or ''}" + (f"\n{link}" if link else "")
    # one body that Slack ("text"), Discord ("content") and Teams/generic receivers all accept
    data = json.dumps({"text": text, "content": text[:1900], "title": title, "body": body, "url": link, "event": payload}, default=str)
    r = httpx.post(url, content=data, headers={"Content-Type": "application/json"}, timeout=20)
    if r.status_code >= 300:
        raise ChannelError(f"webhook {r.status_code}: {r.text[:160]}")


def deliver(channels: list[dict], title: str, body: str, url: str | None, payload: dict) -> list[dict]:
    out = []
    for ch in channels or []:
        t = ch.get("type")
        try:
            if t == "telegram":
                send_telegram(str(ch["chat_id"]), title, body, url)
            elif t == "email":
                send_email(ch["to"], title, body, url)
            elif t == "webhook":
                send_webhook(ch["url"], title, body, url, payload)
            else:
                continue
            out.append({"channel": t, "status": "sent"})
        except Exception as e:  # noqa: BLE001 — one failing channel must not block the others
            out.append({"channel": t, "status": f"error: {str(e)[:200]}"})
    return out


def channel_status() -> dict:
    return {"telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN")), "email": bool(os.getenv("SMTP_HOST")), "webhook": True}


# ------------------------------------------------------------------ matching
class Watch:
    """A subscription's watchlist resolved to ids, for fast matching."""

    def __init__(self, cur, items: list[dict]):
        self.parents, self.companies, self.molecules, self.combos, self.products = set(), set(), set(), set(), set()
        self.mkeys: set[str] = set()
        self.labels: list[str] = []
        for it in items or []:
            key = str(it.get("key", ""))
            typ, _, ref = key.partition(":")
            lab = norm(it.get("label", ""))
            if len(lab) >= 5:
                self.labels.append(lab)
            if typ == "g":
                r = cur.execute("SELECT id FROM parents WHERE slug = ?", [ref]).fetchone()
                if r:
                    self.parents.add(r[0])
                    self.companies |= {x[0] for x in cur.execute("SELECT id FROM companies WHERE parent_id = ?", [r[0]]).fetchall()}
            elif typ == "co":
                r = cur.execute("SELECT id, parent_id FROM companies WHERE slug = ?", [ref]).fetchone()
                if r:
                    self.companies.add(r[0])
            elif typ == "m" and ref.isdigit():
                self.molecules.add(int(ref))
            elif typ == "c" and ref.isdigit():
                self.combos.add(int(ref))
                r = cur.execute("SELECT mkey FROM combos WHERE id = ?", [int(ref)]).fetchone()
                if r:
                    self.mkeys.add(r[0])
                self.molecules |= {x[0] for x in cur.execute(
                    "SELECT DISTINCT pm.molecule_id FROM product_molecules pm JOIN products p ON p.id = pm.product_id WHERE p.combo_id = ?", [int(ref)]).fetchall()}
            elif typ == "p" and ref.isdigit():
                self.products.add(int(ref))
                r = cur.execute("SELECT company_id, combo_id FROM products WHERE id = ?", [int(ref)]).fetchone()
                if r:
                    if r[0]:
                        self.companies.add(r[0])
                    if r[1]:
                        self.combos.add(r[1])
                        mk = cur.execute("SELECT mkey FROM combos WHERE id = ?", [r[1]]).fetchone()
                        if mk:
                            self.mkeys.add(mk[0])
                self.molecules |= {x[0] for x in cur.execute("SELECT molecule_id FROM product_molecules WHERE product_id = ?", [int(ref)]).fetchall()}

    @property
    def empty(self) -> bool:
        return not (self.parents or self.companies or self.molecules or self.combos or self.products or self.labels)

    def match(self, ev: dict) -> str | None:
        et, eid = ev.get("entity_type"), ev.get("entity_id")
        if et == "parent" and eid in self.parents:
            return "watched group"
        if et == "company" and eid in self.companies:
            return "watched company"
        if et == "molecule" and eid in self.molecules:
            return "watched molecule"
        payload = ev.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                payload = {}
        mids = set(payload.get("molecule_ids") or [])
        if mids & self.molecules:
            return "watched molecule"
        if payload.get("mkey") and (payload["mkey"] in self.mkeys or set(payload["mkey"].split("|")) & self._mol_keys()):
            return "watched combination"
        if payload.get("catalog_product_id") in self.products:
            return "watched SKU"
        title = f" {norm(ev.get('title', ''))} "
        for lab in self.labels:
            if f" {lab} " in title:
                return f"mentions {lab}"
        return None

    _mk_cache: set[str] | None = None

    def _mol_keys(self) -> set[str]:
        if self._mk_cache is None:
            if self.molecules:
                q = ",".join(map(str, self.molecules))
                self._mk_cache = {r[0] for r in db.cursor().execute(f"SELECT mkey FROM molecules WHERE id IN ({q})").fetchall()}
            else:
                self._mk_cache = set()
        return self._mk_cache


# ------------------------------------------------------------------ dispatch
def _store(cur, sub_id, event_id, kind, severity, title, body, url, reason, deliveries):
    cur.execute("""INSERT INTO alert_messages (sub_id, event_id, kind, severity, title, body, url, reason, created_at, deliveries)
                   VALUES (?,?,?,?,?,?,?,?, now(), ?)""",
                [sub_id, event_id, kind, severity, title[:500], (body or "")[:4000], url, reason, json.dumps(deliveries)])


def _shelf_flags(csv_text: str) -> dict[str, dict]:
    from .api.routers.shelf import CheckRequest, check
    res = check(CheckRequest(csv=csv_text))
    flags = {}
    for r in res["results"]:
        for f in r["flags"]:
            if f["level"] in ("critical", "warning") and f["code"] not in ("EXPIRING", "EXPIRED", "DISCONTINUED"):
                flags[f"{norm(r['input']['name'])}|{f['code']}|{f.get('source') or ''}"] = {
                    "item": r["input"]["name"], "batch": r["input"].get("batch"), "level": f["level"],
                    "code": f["code"], "message": f["message"], "source": f.get("source")}
    return flags


def dispatch() -> dict:
    """Match new events to every active subscription; send instant alerts and due digests."""
    cur = db.cursor()
    subs = db.rows(cur, "SELECT * FROM alert_subscriptions WHERE active")
    max_eid = cur.execute("SELECT coalesce(max(id), 0) FROM events").fetchone()[0]
    max_nsq = cur.execute("SELECT coalesce(max(id), 0) FROM reg_nsq").fetchone()[0]
    stats = {"subscriptions": len(subs), "messages": 0, "shelf_checks": 0, "digests": 0}
    now = datetime.now(IST)
    for s in subs:
        channels = json.loads(s["channels"]) if isinstance(s["channels"], str) else (s["channels"] or [])
        watch_items = json.loads(s["watch"]) if isinstance(s["watch"], str) else (s["watch"] or [])
        kinds = {k.strip() for k in (s["kinds"] or "").split(",") if k.strip()}
        min_rank = SEV_RANK.get(s["min_severity"] or "info", 0)
        w = Watch(cur, watch_items)
        new_events = db.rows(cur, """SELECT id, ts, kind, severity, title, body, url, source, entity_type, entity_id, payload
                                     FROM events WHERE id > ? ORDER BY id LIMIT 2000""", [s["last_event_id"] or 0])
        if not s["last_event_id"]:
            # a new subscription starts from now rather than replaying history
            new_events = []
        matched = []
        for ev in new_events:
            if kinds and ev["kind"] not in kinds:
                continue
            if SEV_RANK.get(ev["severity"], 0) < min_rank:
                continue
            if w.empty and s["shelf_csv"]:
                continue          # shelf-only subscription: events arrive through the shelf re-check
            reason = "filter" if w.empty else w.match(ev)
            if reason:
                matched.append((ev, reason))
        # NSQ batches for watched makers/molecules (most NSQ rows do not raise events)
        nsq_rows = []
        if (w.companies or w.molecules) and s["last_nsq_id"]:
            for n in db.rows(cur, "SELECT * FROM reg_nsq WHERE id > ? ORDER BY id LIMIT 2000", [s["last_nsq_id"]]):
                mids = {int(x) for x in (n["molecule_ids"] or "").split(",") if x}
                if n["company_id"] in w.companies or mids & w.molecules:
                    nsq_rows.append(n)
        with db.writer() as wr:
            sent_instant = 0
            for ev, reason in matched:
                body = (ev["body"] or "") + (f"\nSource: {ev['source']}" if ev.get("source") else "")
                deliveries = []
                if s["instant"] and sent_instant < MAX_INSTANT_PER_RUN:
                    deliveries = deliver(channels, f"{ev['kind'].upper()}: {ev['title']}", body, ev["url"], ev)
                    sent_instant += 1
                _store(wr, s["id"], ev["id"], "event", ev["severity"], ev["title"], body, ev["url"], reason, deliveries)
                stats["messages"] += 1
            if s["instant"] and len(matched) > MAX_INSTANT_PER_RUN:
                extra = len(matched) - MAX_INSTANT_PER_RUN
                deliver(channels, f"{extra} more alerts", f"See the inbox: {PUBLIC_URL}/alerts", f"{PUBLIC_URL}/alerts", {})
            for n in nsq_rows:
                title = f"{n['category']}: {n['product_text']} batch {n['batch_no']} ({n['manufacturer'] or ''})"
                body = f"{n['reason'] or ''} · {n['alert_month'] or ''} · {n['lab'] or ''}"
                deliveries = deliver(channels, title, body, n["source_url"], {"nsq_id": n["id"]}) if s["instant"] else []
                _store(wr, s["id"], None, "nsq", "high", title, body, n["source_url"], "watched maker/molecule", deliveries)
                stats["messages"] += 1

            # shelf re-check when regulator data that can change flags arrived
            shelf_due = s["shelf_csv"] and (not s["shelf_state"] or any(ev["kind"] in SHELF_TRIGGER_KINDS for ev in new_events))
            if shelf_due:
                stats["shelf_checks"] += 1
                flags = _shelf_flags(s["shelf_csv"])
                old = json.loads(s["shelf_state"]) if isinstance(s["shelf_state"], str) else (s["shelf_state"] or {})
                fresh = [v for k, v in flags.items() if k not in old] if s["shelf_state"] else []
                for f in fresh:
                    title = f"SHELF {'STOP SALE' if f['level'] == 'critical' else 'REVIEW'}: {f['item']}" + (f" batch {f['batch']}" if f.get("batch") else "")
                    deliveries = deliver(channels, title, f["message"], f.get("source") or f"{PUBLIC_URL}/shelf", f) if s["instant"] else []
                    _store(wr, s["id"], None, "shelf", "critical" if f["level"] == "critical" else "high", title, f["message"],
                           f.get("source") or f"{PUBLIC_URL}/shelf", f["code"], deliveries)
                    stats["messages"] += 1
                wr.execute("UPDATE alert_subscriptions SET shelf_state = ? WHERE id = ?", [json.dumps(flags), s["id"]])

            # daily digest
            if s["digest_hour"] is not None and now.hour >= int(s["digest_hour"]) and s["last_digest"] != now.date():
                rows = db.rows(wr, """SELECT severity, title, url FROM alert_messages
                                      WHERE sub_id = ? AND kind <> 'digest' AND created_at >= now() - INTERVAL 1 DAY ORDER BY id""", [s["id"]])
                if rows:
                    lines = [f"• [{r['severity']}] {r['title']}" for r in rows[:60]]
                    body = "\n".join(lines) + (f"\n… and {len(rows) - 60} more" if len(rows) > 60 else "")
                    title = f"Daily digest — {len(rows)} alerts ({s['name']})"
                    deliveries = deliver(channels, title, body, f"{PUBLIC_URL}/alerts", {})
                    _store(wr, s["id"], None, "digest", "info", title, body, f"{PUBLIC_URL}/alerts", "digest", deliveries)
                    stats["digests"] += 1
                wr.execute("UPDATE alert_subscriptions SET last_digest = ? WHERE id = ?", [now.date(), s["id"]])
            wr.execute("UPDATE alert_subscriptions SET last_event_id = ?, last_nsq_id = ? WHERE id = ?", [max_eid, max_nsq, s["id"]])
    return stats


def send_test(sub_id: int) -> dict:
    cur = db.cursor()
    s = db.one(cur, "SELECT * FROM alert_subscriptions WHERE id = ?", [sub_id])
    if not s:
        raise ValueError("subscription not found")
    channels = json.loads(s["channels"]) if isinstance(s["channels"], str) else (s["channels"] or [])
    title = f"Test alert — {s['name']}"
    body = "Your PharmaLens alert route works. Matching bans, NSQ batches, recalls, price notices and news will arrive here."
    deliveries = deliver(channels, title, body, f"{PUBLIC_URL}/alerts", {})
    with db.writer() as wr:
        _store(wr, sub_id, None, "test", "info", title, body, f"{PUBLIC_URL}/alerts", "test", deliveries)
    return {"deliveries": deliveries}
