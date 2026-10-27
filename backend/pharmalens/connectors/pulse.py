"""Pulse: a regular Telegram digest of what the terminal did since the last one (HEALTH_TELEGRAM_CHAT).

Every two hours through the day: feeds run and rows fetched, the newest high-severity events (quality failures,
bans, approvals, recalls, safety alerts), headlines, and pharma share movers in market hours. It reports real
activity only; a quiet window still says which feeds ran, so the bot visibly stays alive.
"""
import html
import os
from datetime import datetime, timedelta

from .. import db
from ..alerts import PUBLIC_URL, send_telegram
from .base import Connector

STATE = "pulse|last"
SEV = {"critical": 0, "high": 1, "medium": 2, "info": 3}


class Pulse(Connector):
    name = "bot_pulse"
    title = "Telegram pulse (activity digest)"
    agency = "PharmaLens"
    schedule = {"trigger": "cron", "hour": "7-23/2", "minute": 5}
    description = "Two-hourly Telegram digest of feeds run, new data, top events, headlines and share movers."

    def run(self):
        chat = os.getenv("HEALTH_TELEGRAM_CHAT")
        if not chat:
            self.stats.notes.append("HEALTH_TELEGRAM_CHAT not set")
            return
        cur = db.cursor()
        last = cur.execute("SELECT value FROM connector_state WHERE key = ?", [STATE]).fetchall()
        since = datetime.fromisoformat(last[0][0]) if last else datetime.now() - timedelta(hours=2)
        now = datetime.now()

        runs = cur.execute("""SELECT connector, count(*), sum(rows_new), sum(events_new), count(*) FILTER (WHERE status = 'error')
                              FROM connector_runs WHERE finished_at > ? AND connector NOT IN ('alerts_dispatch', 'health_watch', 'bot_pulse')
                              GROUP BY 1 ORDER BY 3 DESC NULLS LAST""", [since]).fetchall()
        events = cur.execute("""SELECT severity, kind, title FROM events WHERE detected_at > ? AND kind <> 'news'
                                ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, detected_at DESC
                                LIMIT 6""", [since]).fetchall()
        n_events = cur.execute("SELECT count(*) FROM events WHERE detected_at > ?", [since]).fetchall()[0][0]
        news = cur.execute("""SELECT title, source FROM news WHERE fetched_at > ? AND published_at > ? - INTERVAL 2 DAY
                              ORDER BY published_at DESC LIMIT 3""", [since, now]).fetchall()
        movers = cur.execute("""SELECT p.name, q.change_pct FROM quotes q JOIN parents p ON q.ticker = p.ticker || '.NS'
                                WHERE q.change_pct IS NOT NULL AND q.quoted_at > ? - INTERVAL 6 HOUR
                                ORDER BY abs(q.change_pct) DESC LIMIT 3""", [now]).fetchall()
        totals = cur.execute("""SELECT (SELECT count(*) FROM reg_nsq), (SELECT count(*) FROM sec_items), (SELECT count(*) FROM news),
                                       (SELECT count(*) FROM quote_history)""").fetchall()[0]

        rows_new = sum(r[2] or 0 for r in runs)
        errs = sum(r[4] or 0 for r in runs)
        lines = [f"{since:%H:%M}–{now:%H:%M} · {len(runs)} feeds ran · {rows_new:,} new rows · {n_events} events" + (f" · {errs} errors" if errs else "")]
        busy = [f"{name} +{n:,}" for name, _, n, _, _ in runs if n][:5]
        if busy:
            lines.append("Fetched: " + ", ".join(busy))
        if events:
            lines.append("")
            lines += [f"{'🔴' if s in ('critical', 'high') else '🟠' if s == 'medium' else '⚪'} {t[:140]}" for s, k, t in events]
        if news:
            lines.append("")
            lines += [f"📰 {t[:120]} ({src})" for t, src in news]
        if movers:
            lines.append("")
            lines.append("Movers: " + ", ".join(f"{n} {c:+.1f}%" for n, c in movers))
        lines.append("")
        lines.append(f"Corpus: {totals[0]:,} NSQ batches · {totals[1]:,} SEC items · {totals[2]:,} news · {totals[3]:,} daily closes")
        send_telegram(chat, "PharmaLens pulse", "\n".join(lines), PUBLIC_URL)
        with db.writer() as w:
            w.execute("INSERT OR REPLACE INTO connector_state VALUES (?, ?)", [STATE, now.isoformat()])
        self.stats.rows_new = 1
        self.stats.notes.append(f"pulse sent: {len(runs)} feeds, {rows_new} rows, {n_events} events")
