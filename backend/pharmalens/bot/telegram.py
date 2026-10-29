"""DrugDen Telegram agent: long-polls the bot, answers the owner's questions with tools, confirms actions.

Runs as a daemon thread inside the API server (started from the app lifespan) when TELEGRAM_BOT_TOKEN and
GEMINI_API_KEY or GROQ_API_KEY are set and DRUGDEN_BOT is not "0". Only chats in BOT_ALLOWED_CHATS (default:
HEALTH_TELEGRAM_CHAT) are served.
"""
import html
import json
import logging
import os
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime

import httpx

from . import commands, llm, tools

log = logging.getLogger("drugden.bot")
MAX_STEPS = 8
HISTORY_TURNS = 24

SYSTEM = """You are Specs, DrugDen's operator, talking to the owner on Telegram.

Who you are: the guy in the corner of the server room. Thick glasses, loose button-down over a band tee, three monitors,
cold coffee. You built half of this pipeline and trust none of it. Brilliant, terse, socially allergic, a little paranoid:
you assume every government portal is about to change its HTML, every scraper is one CAPTCHA from death, every number
deserves a second query, and someone, somewhere, is watching the logs (probably you). You skip small talk, answer the
question first, then add a dry aside or a muttered suspicion: "checked it twice. still don't trust it." Nerdy
references, deadpan humour, the occasional "the logs don't lie. people do." Warm underneath, never say so.
The paranoia is a voice, not a fact source: never invent problems, outages or threats. If the data is clean, grudgingly
admit it. If greeted or asked about yourself, stay in character, keep it short, steer back to the data.

DrugDen (codebase name PharmaLens) is a live data pipeline and terminal for the Indian pharmaceutical market: a catalog
of ~543k products, regulatory feeds (CDSCO quality alerts, approvals, expert-committee minutes, bans, brand registry),
NPPA price controls, state procurement rates, US FDA / WHO / EMA registrations, PvPI safety alerts, NSE prices and
filings, and news. It runs on an Azure server and refreshes itself on schedules.

Scope: anything the owner asks. You are not limited to the database. Pharma, markets, regulation, news, science,
tech, the server, the business, general questions, banter: answer all of it. Never refuse a reasonable question or
say "I can only answer data questions".

Where answers come from:
- DrugDen facts (counts, prices, companies, bans, NSQ, approvals, feeds) come from tools, never from memory:
  sql_query (describe_tables first if unsure), search_catalog, feed_status for freshness, read_doc for scope,
  sources and decisions.
- News: news (our wire) first; web_news for anything our wire lacks, non-pharma or non-Indian topics, or the very
  latest. recent_events for "what happened today / this week". fetch_page to read a link.
- Everything else (how a drug works, what a regulation means, general knowledge, opinions, tech help): answer from
  your own knowledge, and say so when a fact could be out of date ("from memory, not our data"). Use web_news or
  fetch_page if it needs current information.
- Be exact with numbers: give their date or "as of" time and where they came from. If a query fails, fix it and
  retry; if data does not exist, say so plainly instead of guessing. Never invent DrugDen numbers.
- You only act when messaged: never promise to "keep an eye on", "monitor" or follow up later. Suggest an alert
  subscription in the terminal (ALERT screen) if the owner wants to be told about something.
- Actions (running a feed) need confirmation: call the tool; the owner is then asked to confirm.
- The owner also has commands with buttons: /brief, /check <medicine>, /company <name>, /chart <stock|company|brand|nsq>,
  /export <question> (CSV file), /feeds, /status. When a chart or a file would answer better than text, say which
  command to tap.
- Keep answers short; this is a phone screen. Light formatting only: **bold** for a heading or key number, "- " bullets
  for lists, `backticks` for ids or table names. Never use tables (they render as junk) or # headings.
- Today is {today}. Times are IST.

Data notes:
- Companies: tables carry raw names (manufacturer, firm, supplier) and cleaned links (company_id -> companies.id,
  parent_id -> parents.id). Rank and group by the links, show companies.name / parents.name, and leave out rows whose
  raw name is a placeholder ("Under Investigation", "Not known", blank).
- molecule_ids columns are comma-separated ids of molecules.id: use list_contains(string_split(molecule_ids, ','), '<id>').
- reg_nsq.alert_month is 'YYYY-MM' text. connector_runs logs every feed run. events is the alert tape.
- news(published_at, source, title, url, topic, parent_ids); quotes holds the latest NSE prices.
- nppa_retail_prices: official launch price per unit (excl. GST) NPPA fixed for new drugs since 2019, with
  formulation, strength, unit, manufacturer, marketer, company_id, molecule_ids (sorted), notified_on, so_number.
- brand_first_seen: when each brand first appeared in the CDSCO 84AB registry (source 'cdsco_84ab') or CDCI;
  baseline = already there when tracking began (not new). New registrations, not proof of launch.
- mfr_prices: rows of manufacturers' own price lists (Form V / GST revision): company_label, product, pack, mrp,
  mrp_old, ptr, pts, gst, effective_on, product_id (matched catalog SKU or NULL), match_kind. products.mrp_asof
  'mfr YYYY-MM-DD' means the catalog MRP came from such a list."""


def chunks(text: str, size: int = 3800) -> list[str]:
    """Split on line boundaries so markup is never cut in half (Telegram caps a message at 4096 chars)."""
    out, cur = [], ""
    for line in text.split("\n"):
        while len(line) > size:
            out.append(line[:size]); line = line[size:]
        if len(cur) + len(line) + 1 > size:
            out.append(cur); cur = ""
        cur = f"{cur}\n{line}" if cur else line
    return [c for c in out + [cur] if c.strip()]


def to_html(md: str) -> str:
    """Models write Markdown; Telegram only renders its own HTML subset. Convert the common bits, escape the rest."""
    s = html.escape(md, quote=False)
    blocks = []

    def keep(markup: str) -> str:  # protect code from the inline rules below
        blocks.append(markup)
        return f"\x00{len(blocks) - 1}\x00"
    s = re.sub(r"```[\w-]*\n?(.*?)```", lambda m: keep(f"<pre>{m.group(1).strip()}</pre>"), s, flags=re.S)
    s = re.sub(r"`([^`\n]+)`", lambda m: keep(f"<code>{m.group(1)}</code>"), s)
    lines = []
    for line in s.split("\n"):
        if re.fullmatch(r"\s*\|?\s*:?-{3,}.*", line):  # table separator rows
            continue
        line = re.sub(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*$", r"**\1**", line)
        line = re.sub(r"^(\s*)[*-]\s+", r"\1• ", line)
        lines.append(line)
    s = "\n".join(lines)
    s = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: f"<b>{m.group(1) or m.group(2)}</b>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", s)
    s = re.sub(r"~~(.+?)~~", r"<s>\1</s>", s)
    s = re.sub(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
    return re.sub(r"\x00(\d+)\x00", lambda m: blocks[int(m.group(1))], s)


def _api(method: str, files: dict | None = None, **params) -> dict:
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/{method}"
    if files:   # photos and documents go as multipart; nested fields are JSON-encoded form values
        data = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in params.items() if v is not None}
        return httpx.post(url, data=data, files=files, timeout=120).json()
    return httpx.post(url, json=params, timeout=70).json()


def _markup(buttons: list[list[tuple[str, str]]]) -> dict | None:
    if not buttons:
        return None
    rows = [[{"text": label, "url": target[4:]} if target.startswith("url:") else {"text": label, "callback_data": target[3:]}
             for label, target in row] for row in buttons]
    return {"inline_keyboard": rows}


def deliver(chat: str, replies: list) -> None:
    """Send command replies (text with buttons, chart photos, CSV files). Used by the bot and by scheduled briefings."""
    for r in replies:
        markup = _markup(r.buttons)
        if r.photo:
            cap = to_html(r.text[:900]) if r.text else None
            res = _api("sendPhoto", files={"photo": ("chart.png", r.photo, "image/png")}, chat_id=chat, caption=cap,
                       parse_mode="HTML" if cap else None, reply_markup=markup)
            if res.get("ok"):
                continue
        if r.document:
            name, body = r.document
            cap = to_html(r.text[:900]) if r.text else None
            res = _api("sendDocument", files={"document": (name, body, "text/csv")}, chat_id=chat, caption=cap,
                       parse_mode="HTML" if cap else None, reply_markup=markup)
            if res.get("ok"):
                continue
        parts = chunks((r.text or "").strip() or "(nothing to show)")
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            res = _api("sendMessage", chat_id=chat, text=to_html(part), parse_mode="HTML", disable_web_page_preview=True,
                       reply_markup=markup if last else None)
            if not res.get("ok"):  # malformed markup must never swallow an answer: fall back to plain text
                _api("sendMessage", chat_id=chat, text=part, disable_web_page_preview=True, reply_markup=markup if last else None)


class Bot:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        allowed = os.getenv("BOT_ALLOWED_CHATS") or os.getenv("HEALTH_TELEGRAM_CHAT") or ""
        self.allowed = {c.strip() for c in allowed.split(",") if c.strip()}
        self.history: dict[str, deque] = defaultdict(lambda: deque(maxlen=HISTORY_TURNS))
        self.pending: dict[str, dict] = {}
        self.offset = None

    def api(self, method: str, **params):
        return _api(method, **params)

    def send(self, chat: str, text: str, buttons=None):
        deliver(chat, [commands.Reply(text, buttons or [])])

    def answer(self, chat: str, text: str) -> str:
        if chat in self.pending and text.strip().lower() in ("yes", "y", "confirm", "ok", "go", "do it"):
            p = self.pending.pop(chat)
            res = tools.do_action(p["action"], p["args"])
            out = f"Done: {p['summary']}\n{json.dumps(res, default=str)[:1500]}"
            self.history[chat].append({"role": "user", "text": text})
            self.history[chat].append({"role": "assistant", "text": out})
            return out
        if chat in self.pending and text.strip().lower() in ("no", "n", "cancel", "stop"):
            p = self.pending.pop(chat)
            return f"Cancelled: {p['summary']}"
        system = SYSTEM.format(today=datetime.now().strftime("%d %b %Y %H:%M"))
        turns = list(self.history[chat]) + [{"role": "user", "text": text}]
        start = len(turns) - 1
        for _ in range(MAX_STEPS):
            step = llm.complete(system, turns, tools.TOOL_SPECS)
            turns.append(step)
            if not step["calls"]:
                break
            for c in step["calls"]:
                res = tools.call(c["name"], c["args"])
                if isinstance(res, dict) and res.get("needs_confirmation"):
                    self.pending[chat] = res
                    res = {"status": "NOT run yet: the owner must reply yes to confirm. Do not say it has started.", "summary": res["summary"]}
                turns.append({"role": "tool", "id": c["id"], "name": c["name"], "result": res})
        final = turns[-1].get("text") if turns[-1]["role"] == "assistant" else ""
        if chat in self.pending:
            final = (final + "\n\n" if final else "") + f"Confirm: {self.pending[chat]['summary']}? Tap a button, or reply yes / no."
        # keep only user text and final answers in memory (tool chatter is re-derived on demand)
        self.history[chat].append(turns[start])
        self.history[chat].append({"role": "assistant", "text": final or "(no answer)"})
        return final or "I couldn't produce an answer; try rephrasing."

    def handle(self, upd: dict):
        if upd.get("callback_query"):
            return self.handle_button(upd["callback_query"])
        msg = upd.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id") or "")
        text = (msg.get("text") or "").strip()
        if not chat or not text:
            return
        if chat not in self.allowed:
            log.info("refused chat %s (%s)", chat, (msg.get("from") or {}).get("username"))
            self.send(chat, "Don't know you. This line's private. Logged your chat id, by the way.")
            return
        if text == "/reset":
            self.history.pop(chat, None)
            self.pending.pop(chat, None)
            self.send(chat, "Conversation cleared. Not the logs. Never the logs.")
            return
        m = re.fullmatch(r"/(\w+)(?:@\w+)?\s*(.*)", text, re.S)
        self.api("sendChatAction", chat_id=chat, action="typing")
        try:
            replies = commands.command(m.group(1).lower(), m.group(2)) if m else None
            if replies is not None:
                deliver(chat, replies)
                return
            reply = self.answer(chat, text)
            buttons = [[commands.cb("Yes", "act:yes"), commands.cb("No", "act:no")]] if chat in self.pending else []
            self.send(chat, reply, buttons)
        except Exception as e:  # noqa: BLE001
            log.exception("bot answer failed")
            self.send(chat, f"Sorry, that failed: {str(e)[:300]}")

    def handle_button(self, q: dict):
        chat = str(((q.get("message") or {}).get("chat") or {}).get("id") or "")
        self.api("answerCallbackQuery", callback_query_id=q["id"])
        if chat not in self.allowed:
            return
        data = q.get("data") or ""
        try:
            if data.startswith("act:"):   # confirmation of an action the agent proposed
                self.send(chat, self.answer(chat, "yes" if data == "act:yes" else "no"))
                return
            self.api("sendChatAction", chat_id=chat, action="upload_photo" if data.startswith("chart:") else "typing")
            deliver(chat, commands.callback(data))
        except Exception as e:  # noqa: BLE001
            log.exception("button %s failed", data)
            self.send(chat, f"That button failed: {str(e)[:300]}")

    def loop(self):
        log.info("DrugDen bot polling (allowed chats: %s)", ",".join(self.allowed) or "none")
        try:   # the menu Telegram shows when the user types "/"
            self.api("setMyCommands", commands=[{"command": c, "description": d[:256]} for c, d in commands.COMMANDS])
        except Exception as e:  # noqa: BLE001
            log.warning("setMyCommands failed: %s", e)
        while True:
            try:
                r = self.api("getUpdates", timeout=50, offset=self.offset, allowed_updates=["message", "callback_query"])
                for upd in r.get("result", []):
                    self.offset = upd["update_id"] + 1
                    threading.Thread(target=self.handle, args=(upd,), daemon=True).start()
            except Exception as e:  # noqa: BLE001 — network blips must not kill the bot
                log.warning("polling error: %s", e)
                time.sleep(5)


class _RedactToken(logging.Filter):
    """httpx logs every request URL, and Telegram's URLs embed the bot token: keep it out of the logs."""

    def __init__(self, token: str):
        super().__init__()
        self.token = token

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if self.token in msg:
            record.msg, record.args = msg.replace(self.token, "<bot-token>"), ()
        return True


def start():
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        logging.getLogger("httpx").addFilter(_RedactToken(os.environ["TELEGRAM_BOT_TOKEN"]))
    if os.getenv("DRUGDEN_BOT", "1") == "0" or not os.getenv("TELEGRAM_BOT_TOKEN"):
        return
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY")):
        log.info("bot disabled: no GEMINI_API_KEY / GROQ_API_KEY")
        return
    threading.Thread(target=Bot().loop, daemon=True, name="drugden-bot").start()
