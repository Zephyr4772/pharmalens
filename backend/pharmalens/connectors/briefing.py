"""Briefings to Telegram (HEALTH_TELEGRAM_CHAT): a morning brief and an evening wrap.

Each covers everything since the previous briefing, ranked by importance and written up by the model from the
database's facts (bot/briefing.py), with buttons for the full event list, a chart and the feed board. Replaces the
two-hourly pulse, which listed raw activity counts.
"""
import os
from datetime import datetime, timedelta

from .. import db
from .base import Connector

STATE = "briefing|last"


class Briefing(Connector):
    name = "bot_briefing"
    title = "Telegram briefings (morning and evening)"
    agency = "PharmaLens"
    schedule = {"trigger": "cron", "hour": "8,19", "minute": 30}
    description = "Morning brief and evening wrap on Telegram: what happened since the last one and why it matters."

    def run(self):
        from ..bot import briefing, commands
        from ..bot.telegram import deliver
        chat = os.getenv("HEALTH_TELEGRAM_CHAT")
        if not chat or not os.getenv("TELEGRAM_BOT_TOKEN"):
            self.stats.notes.append("HEALTH_TELEGRAM_CHAT / TELEGRAM_BOT_TOKEN not set")
            return
        cur = db.cursor()
        last = cur.execute("SELECT value FROM connector_state WHERE key = ?", [STATE]).fetchone()
        now = datetime.now()
        since = datetime.fromisoformat(last[0]) if last else now - timedelta(hours=12)
        since = max(since, now - timedelta(hours=36))      # after downtime, brief the last day and a half, not a week
        text, facts = briefing.write(briefing.label_for(now), since)
        hours = max(1, round((now - since).total_seconds() / 3600))
        deliver(chat, [commands.Reply(text, commands.brief_buttons(hours))])
        with db.writer() as w:
            w.execute("INSERT OR REPLACE INTO connector_state VALUES (?, ?)", [STATE, now.isoformat()])
        self.stats.rows_new = 1
        self.stats.notes.append(f"{briefing.label_for(now)} sent: {len(facts['top_events'])} top events, "
                                f"{(facts['quality_failures'] or {}).get('batches', 0)} failed batches, {len(facts['news'])} news")
