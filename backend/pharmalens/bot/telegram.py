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

from . import llm, tools

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

Rules:
- Answer from tools, never from memory. For data questions, query the database (describe_tables if unsure, then
  sql_query). For freshness or "is X working", use feed_status. For what the product is, its scope, sources and
  decisions, use read_doc.
- Be exact: give numbers with their date or "as of" time, and say which table or source they came from.
- If a query fails, fix it and retry; if data does not exist, say so plainly instead of guessing.
- Actions (running a feed) need confirmation: call the tool; the owner is then asked to confirm.
- Keep answers short; this is a phone screen. Light formatting only: **bold** for a heading or key number, "- " bullets
  for lists, `backticks` for ids or table names. Never use tables (they render as junk) or # headings.
- Today is {today}. Times are IST.

Data notes:
- Companies: tables carry raw names (manufacturer, firm, supplier) and cleaned links (company_id -> companies.id,
  parent_id -> parents.id). Rank and group by the links, show companies.name / parents.name, and leave out rows whose
  raw name is a placeholder ("Under Investigation", "Not known", blank).
- molecule_ids columns are comma-separated ids of molecules.id: use list_contains(string_split(molecule_ids, ','), '<id>').
- reg_nsq.alert_month is 'YYYY-MM' text. connector_runs logs every feed run. events is the alert tape."""


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


class Bot:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        allowed = os.getenv("BOT_ALLOWED_CHATS") or os.getenv("HEALTH_TELEGRAM_CHAT") or ""
        self.allowed = {c.strip() for c in allowed.split(",") if c.strip()}
        self.history: dict[str, deque] = defaultdict(lambda: deque(maxlen=HISTORY_TURNS))
        self.pending: dict[str, dict] = {}
        self.offset = None

    def api(self, method: str, **params):
        r = httpx.post(f"https://api.telegram.org/bot{self.token}/{method}", json=params, timeout=70)
        return r.json()

    def send(self, chat: str, text: str):
        for part in chunks(text.strip() or "(no answer)"):
            r = self.api("sendMessage", chat_id=chat, text=to_html(part), parse_mode="HTML", disable_web_page_preview=True)
            if not r.get("ok"):  # malformed markup must never swallow an answer: fall back to plain text
                self.api("sendMessage", chat_id=chat, text=part, disable_web_page_preview=True)

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
            final = (final + "\n\n" if final else "") + f"Confirm: {self.pending[chat]['summary']}? Reply yes or no."
        # keep only user text and final answers in memory (tool chatter is re-derived on demand)
        self.history[chat].append(turns[start])
        self.history[chat].append({"role": "assistant", "text": final or "(no answer)"})
        return final or "I couldn't produce an answer; try rephrasing."

    def handle(self, upd: dict):
        msg = upd.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id") or "")
        text = msg.get("text") or ""
        if not chat or not text:
            return
        if chat not in self.allowed:
            log.info("refused chat %s (%s)", chat, (msg.get("from") or {}).get("username"))
            self.send(chat, "Don't know you. This line's private. Logged your chat id, by the way.")
            return
        if text.strip() in ("/start", "/help"):
            self.send(chat, "**Specs.** Yeah, I run the pipes here.\n"
                            "Ask about the data, how fresh it is, sources, any drug or company. I can kick off a feed too, "
                            "but I'll make you confirm. I don't do surprises.\n"
                            "/reset wipes our chat. Not the logs. Never the logs.")
            return
        if text.strip() == "/reset":
            self.history.pop(chat, None)
            self.pending.pop(chat, None)
            self.send(chat, "Conversation cleared.")
            return
        self.api("sendChatAction", chat_id=chat, action="typing")
        try:
            reply = self.answer(chat, text)
        except Exception as e:  # noqa: BLE001
            log.exception("bot answer failed")
            reply = f"Sorry, that failed: {str(e)[:300]}"
        self.send(chat, reply)

    def loop(self):
        log.info("DrugDen bot polling (allowed chats: %s)", ",".join(self.allowed) or "none")
        while True:
            try:
                r = self.api("getUpdates", timeout=50, offset=self.offset, allowed_updates=["message"])
                for upd in r.get("result", []):
                    self.offset = upd["update_id"] + 1
                    threading.Thread(target=self.handle, args=(upd,), daemon=True).start()
            except Exception as e:  # noqa: BLE001 — network blips must not kill the bot
                log.warning("polling error: %s", e)
                time.sleep(5)


def start():
    if os.getenv("DRUGDEN_BOT", "1") == "0" or not os.getenv("TELEGRAM_BOT_TOKEN"):
        return
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY")):
        log.info("bot disabled: no GEMINI_API_KEY / GROQ_API_KEY")
        return
    threading.Thread(target=Bot().loop, daemon=True, name="drugden-bot").start()
