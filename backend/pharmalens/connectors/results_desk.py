"""Specs' results desk on Telegram (HEALTH_TELEGRAM_CHAT): previews on results mornings, summaries once results are
filed, and a weekly digest. The text is built in bot/desk.py; these feeds only decide when and what is new.
"""
import os
from datetime import datetime, timedelta

from .. import db
from .base import Connector


def _chat(stats) -> str | None:
    chat = os.getenv("HEALTH_TELEGRAM_CHAT")
    if not chat or not os.getenv("TELEGRAM_BOT_TOKEN"):
        stats.notes.append("HEALTH_TELEGRAM_CHAT / TELEGRAM_BOT_TOKEN not set")
        return None
    return chat


class ResultsPreview(Connector):
    name = "results_preview"
    title = "Results-day previews (Telegram)"
    agency = "PharmaLens"
    schedule = {"trigger": "cron", "hour": 7, "minute": 45}
    description = "On a results morning: the bar each watched company has to clear, margin trend, stock and open flags."

    def run(self):
        from ..bot import desk
        from ..bot.telegram import deliver
        if not (chat := _chat(self.stats)):
            return
        out = desk.previews_for(datetime.now().date())
        if out:
            deliver(chat, out)
        self.stats.rows_new = len(out)
        self.stats.notes.append(f"{len(out)} preview messages")


SUMMARY_STATE = "desk|summary_last"


class ResultsSummary(Connector):
    name = "results_summary"
    title = "Results summaries (Telegram)"
    agency = "PharmaLens"
    schedule = {"trigger": "cron", "hour": "10-23/2", "minute": 35}   # 15 minutes after each nse_results run
    description = "Newly filed quarterly results: full summary with chart for watched companies, one line each for the rest."

    def run(self):
        from ..bot import charts, desk
        from ..bot.commands import Reply
        from ..bot.telegram import deliver
        if not (chat := _chat(self.stats)):
            return
        cur = db.cursor()
        last = cur.execute("SELECT value FROM connector_state WHERE key = ?", [SUMMARY_STATE]).fetchone()
        # first run: start from now, so a backlog of old filings is not replayed
        since = datetime.fromisoformat(last[0]) if last else datetime.now()
        # a filing also rewrites the comparison quarters it carries, so only each company's newest quarter counts,
        # and each (company, quarter) is summarised once
        new = cur.execute("""SELECT f.symbol, f.period_end, max(f.fetched_at) FROM fin_results f
                             WHERE f.consolidated AND date_diff('day', f.period_start, f.period_end) < 100 AND f.fetched_at > ?
                             AND f.filed_at >= now() - INTERVAL 3 DAY          -- fresh filings only, never a re-parse
                             AND f.period_end = (SELECT max(period_end) FROM fin_results x WHERE x.symbol = f.symbol AND x.consolidated)
                             AND NOT EXISTS (SELECT 1 FROM connector_state s WHERE s.key = 'desk|sum|' || f.symbol || '|' || CAST(f.period_end AS VARCHAR))
                             GROUP BY 1, 2 ORDER BY 3""", [since]).fetchall()
        replies, batch = [], []
        for sym, pe, _ in new:
            s = desk.summary(sym, pe)
            if not s:
                continue
            reply, watched = s
            if watched:
                name = reply.text.split("**")[1].split(" Q")[0]
                photo = charts.fin_quarters(sym, name)
                replies.append(Reply(reply.text, reply.buttons, photo=photo) if photo else reply)
            elif line := desk.batch_line(sym, pe):
                batch.append(line)
        if batch:
            replies.append(Reply("**Results in**\n" + "\n".join(batch) + "\n`/fin <name>` for detail.", [[desk.cb("Results calendar", "results:")]]))
        if replies:
            deliver(chat, replies)
        if new:
            with db.writer() as w:
                w.execute("INSERT OR REPLACE INTO connector_state VALUES (?, ?)", [SUMMARY_STATE, str(max(r[2] for r in new))])
                for sym, pe, _ in new:
                    w.execute("INSERT OR REPLACE INTO connector_state VALUES (?, ?)", [f"desk|sum|{sym}|{pe}", datetime.now().isoformat()])
        elif not last:
            with db.writer() as w:
                w.execute("INSERT OR REPLACE INTO connector_state VALUES (?, ?)", [SUMMARY_STATE, since.isoformat()])
        self.stats.rows_new = len(new)
        self.stats.notes.append(f"{len(new)} new quarters; {len(replies) - (1 if batch else 0)} full summaries, {len(batch)} batched")


class WeeklyDigest(Connector):
    name = "weekly_digest"
    title = "Weekly digest (Telegram)"
    agency = "PharmaLens"
    schedule = {"trigger": "cron", "day_of_week": "sat", "hour": 10, "minute": 0}
    description = "Saturday digest: watchlist week, results season scoreboard, new governance flags, next week's calendar."

    def run(self):
        from ..bot import desk
        from ..bot.telegram import deliver
        if not (chat := _chat(self.stats)):
            return
        deliver(chat, [desk.weekly()])
        self.stats.rows_new = 1
        self.stats.notes.append(f"digest sent for the week to {datetime.now() - timedelta(days=0):%d %b}")
