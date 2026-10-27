"""Keep live catalog groupings in step with the seed without a full rebuild.

New parent groups added to seed/parents.json are appended to the parents table (existing ids never move: ids
follow seed order and new groups are appended), companies without a parent are matched against the patterns,
and market share is recomputed so the new groups show up in share tables.
"""
import json

from .. import db, derived, matcher
from ..config import SEED_DIR
from ..normalize import slugify
from .base import Connector


class ParentSync(Connector):
    name = "parent_sync"
    title = "Catalog: parent groups sync"
    agency = "PharmaLens"
    schedule = {"trigger": "cron", "day_of_week": "sun", "hour": 5, "minute": 30}
    description = "Adds new parent groups from the seed, links unparented companies to them, refreshes market share."

    def run(self):
        seed = json.loads((SEED_DIR / "parents.json").read_text(encoding="utf-8"))
        with db.writer() as w:
            have = {r[0] for r in w.execute("SELECT id FROM parents").fetchall()}
            for i, p in enumerate(seed):
                if i + 1 in have:
                    continue
                w.execute("INSERT INTO parents (id, slug, name, ticker, hq, ownership, notes) VALUES (?,?,?,?,?,?,?)",
                          [i + 1, slugify(p["name"]), p["name"], p.get("ticker"), p.get("hq"), p.get("ownership"), p.get("notes")])
                self.stats.rows_new += 1
        merged = 0
        with db.writer() as w:
            ids = {slugify(p["name"]): i + 1 for i, p in enumerate(seed)}
            for i, p in enumerate(seed):
                w.execute("UPDATE parents SET notes = ? WHERE id = ? AND notes IS DISTINCT FROM ?", [p.get("notes"), i + 1, p.get("notes")])
                target = ids.get(slugify(p["merged_into"])) if p.get("merged_into") else None
                if target:
                    n = w.execute("SELECT count(*) FROM companies WHERE parent_id = ?", [i + 1]).fetchall()[0][0]
                    if n:
                        w.execute("UPDATE companies SET parent_id = ? WHERE parent_id = ?", [target, i + 1])
                        merged += n
        matcher.reset()
        linked = merged
        companies = db.cursor().execute("SELECT id, name, name_norm FROM companies WHERE parent_id IS NULL").fetchall()
        updates = [(pid, cid) for cid, name, nn in companies if (pid := matcher.parent_for(name) or matcher.parent_for(nn or ""))]
        with db.writer() as w:
            for pid, cid in updates:
                w.execute("UPDATE companies SET parent_id = ? WHERE id = ?", [pid, cid])
                linked += 1
            if linked or self.stats.rows_new:
                derived.refresh_market_share(w)
        self.stats.rows_seen = len(companies)
        self.stats.notes.append(f"{self.stats.rows_new} new groups · {linked} companies linked ({merged} via mergers)")


class NppaHistory(Connector):
    name = "nppa_history"
    title = "NPPA ceiling price history"
    agency = "NPPA"
    schedule = {"trigger": "cron", "day_of_week": "tue", "hour": 11, "minute": 20}
    description = "Ceiling prices notified in 2011, 2015 and 2022 plus a yearly snapshot of the official compendium."

    def run(self):
        import csv
        from datetime import date
        from ..normalize import molecule_key
        import re
        cur = db.cursor()
        mol = dict(cur.execute("SELECT mkey, id FROM molecules").fetchall())
        years = {r[0] for r in cur.execute("SELECT DISTINCT year FROM nppa_ceiling_history").fetchall()}
        rows = []
        if not years & {2011, 2015, 2022}:
            with open(SEED_DIR / "nppa_ceiling_history.csv", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    rows.append((int(r["year"]), mol.get(molecule_key(r["molecule_name"])), r["molecule_name"], r["dosage_form_strength"],
                                 float(r["ceiling_price"]), r["unit"], r["notification"], "NPPA notification (master dataset)"))
        y = date.today().year
        if y not in years:
            for name, fs, cp, unit, note in cur.execute("""SELECT molecule_name, form_strength, ceiling_price, unit, notification
                                                         FROM nppa_ceiling WHERE source LIKE 'NPPA compendium%'""").fetchall():
                rows.append((y, mol.get(molecule_key(re.sub(r"\(.*?\)", " ", name or ""))) if "+" not in (name or "") else None,
                             name, fs, cp, unit, note, "NPPA compendium snapshot"))
        if rows:
            with db.writer() as w:
                w.executemany("INSERT INTO nppa_ceiling_history VALUES (?,?,?,?,?,?,?,?)", rows)
        self.stats.rows_new = len(rows)
        self.stats.notes.append(f"{len(rows)} rows added; years now {sorted(years | {r[0] for r in rows})}")
