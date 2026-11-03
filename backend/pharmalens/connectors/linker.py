"""Derived links (pharmalens.linking): re-resolves records into molecule / combo / company / group links daily,
after the morning feeds. Writes only the linking tables; source tables are never modified."""
from .base import Connector


class EntityLinker(Connector):
    name = "entity_linker"
    title = "Entity linker (derived links)"
    agency = "PharmaLens"
    schedule = {"trigger": "cron", "hour": 5, "minute": 10}
    description = "Resolves registry, recall, trial, news and tender text into links, with method, confidence and licence."

    def run(self):
        from ..linking import run
        res = run()
        self.stats.rows_new = sum(r.get("links", 0) for r in res)
        failed = [r for r in res if r.get("error")]
        self.stats.notes.append("; ".join(f"{r['linker']}: {r.get('links', 0):,} ({r.get('high', 0):,} high)" for r in res if not r.get("error")))
        if failed:   # the other items ran; the run is still recorded as an error so the failure alert fires
            raise RuntimeError("; ".join(f"{r['linker']}: {r['error']}" for r in failed) + " | " + self.stats.notes[-1])
