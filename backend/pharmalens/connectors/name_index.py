"""Daily rebuild of the bot's name index (data/name_index.json): every group, company, molecule and index with its
short forms, tickers, nicknames and initials, so new companies and molecules are understood the day they appear."""
from .base import Connector


class NameIndex(Connector):
    name = "name_index"
    title = "Bot name index (companies, groups, molecules)"
    agency = "PharmaLens"
    schedule = {"trigger": "cron", "hour": 5, "minute": 45}
    description = "Rebuilds the name index the Telegram bot uses to understand company and drug names in any form."

    def run(self):
        from ..bot import names
        out = names.build()
        n = len(out["entries"])
        aliases = sum(len(e["aliases"]) for e in out["entries"])
        self.stats.rows_seen = n
        self.stats.notes.append(f"{n:,} entities, {aliases:,} name forms")
