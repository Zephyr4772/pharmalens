"""Roadmap #9: every entity an event is about, in event_entities (events.entity_type/entity_id hold only one).

Sources, strongest first:
  event_primary         the entity the connector set (1.0)
  source_record         the event's own record, joined by its dedupe key: news article, NSE filing, trial, US FDA
                        recall, Jan Aushadhi item, ticker (1.0 / 0.95)
  payload_molecule_ids  molecule ids the connector resolved when it raised the event (0.95)
  product_text          molecules resolved from the structured product part of the headline ("NSQ: <product> batch",
                        "SEC recommends ...: <drug>", "(<generic>)"), with the same exact-dictionary resolver and
                        complete / partial confidence as #4; prose is never resolved
  company_group         the group of a linked company (inherits the company link's confidence)
  ingredient_set        the full ingredient set, only when the product text resolved completely and agrees with
                        the payload, so a quality or regulatory record never reaches a combination on a partial match
"""
import json
import re

import pandas as pd

from .. import db
from .molecules import _index, clean_recall, resolve
from .store import HIGH, ensure, licence_of

# where the product description sits in each kind of headline
SEGMENT = {
    "nsqrow": r"^(?:NSQ|SPURIOUS):\s*(.*?)\s+batch\b", "nsqportal": r"^(?:NSQ|SPURIOUS):\s*(.*?)\s+batch\b",
    "sec": r":\s*(.*?)(?:\s+—\s+|$)", "appr": r"\):\s*(.*?)(?:\s+—\s+|$)", "debar": r"\byr:\s*(.*)$",
    "newbrand": r"\(([^()]*)\)\s*$", "whopq": r"prequalification:\s*(.*?)(?:\s+—\s+|$)", "fda": r"recall\s+—\s+[^:]+:\s*(.*)$",
}


def run() -> dict:
    ensure()
    cur = db.cursor()
    idx = _index()
    ev = cur.execute("SELECT id, kind, title, entity_type, entity_id, dedupe_key, CAST(payload AS VARCHAR) FROM events").fetchall()
    news = {u: (str(i), p, m) for i, u, p, m in cur.execute("SELECT id, url, parent_ids, molecule_ids FROM news").fetchall()}
    nse = dict(cur.execute("SELECT seq_id, parent_id FROM corp_announcements").fetchall())
    trials = {n: (p, m) for n, p, m in cur.execute("SELECT nct_id, parent_id, molecule_ids FROM trials").fetchall()}
    fda = {str(i): p for i, p in cur.execute("SELECT id, parent_id FROM usfda_actions").fetchall()}
    ja = {str(c): m for c, m in cur.execute("SELECT drug_code, molecule_ids FROM jan_aushadhi").fetchall()}
    tick = {t: i for i, t in cur.execute("SELECT id, ticker FROM parents WHERE ticker IS NOT NULL").fetchall()}
    group_of = dict(cur.execute("SELECT id, parent_id FROM companies WHERE parent_id IS NOT NULL").fetchall())
    hl = {}
    for st, sk, did in cur.execute(f"""SELECT src_table, src_key, dst_id FROM entity_links WHERE dst_type = 'molecule' AND confidence >= {HIGH}
                                       AND src_table IN ('news', 'trials', 'usfda_actions')""").fetchall():
        hl.setdefault((st, sk), set()).add(did)
    lic = licence_of("events")

    rows = []

    def add(eid, et, ei, method, conf, evid):
        if ei is None or ei == "":
            return
        rows.append({"event_id": eid, "entity_type": et, "entity_id": str(ei), "method": method, "confidence": conf,
                     "evidence": evid[:300], "licence": lic})

    for eid, kind, title, etype, eidv, key, payload in ev:
        pre, _, rest = (key or "").partition("|")
        if etype and eidv is not None:
            add(eid, etype, eidv, "event_primary", 1.0, "entity set by the connector")
        pl = json.loads(payload) if payload else {}
        pl_mols = {str(m) for m in (pl.get("molecule_ids") or [])}
        # molecules from the structured product part of the headline
        rx = SEGMENT.get(pre)
        seg = None
        if rx and title:
            m = re.search(rx, title)
            seg = m.group(1).strip() if m else None
            if seg and pre == "fda":
                seg = clean_recall(seg)
        found = resolve(seg, True, idx) if seg else []
        seen = {str(f[0]) for f in found}
        for m in pl_mols:
            # connectors sometimes resolved a whole composition (excipients included): ids the headline's product text
            # does not confirm stay inferred
            if m in seen or not rx:
                add(eid, "molecule", m, "payload_molecule_ids", 0.95, "molecule ids resolved by the connector")
            else:
                add(eid, "molecule", m, "payload_molecule_ids_unconfirmed", 0.7, f"connector id not found in “{(seg or title or '')[:120]}”")
        # the event's own record
        if pre == "news" and rest in news:
            nid, p, m = news[rest]
            for x in (p or "").split(","):
                add(eid, "parent", x.strip(), "source_record", 0.95, "news article's group tags")
            for x in set((m or "").split(",")) | hl.get(("news", nid), set()):
                add(eid, "molecule", x.strip(), "source_record", 0.95, "news article's molecule tags")
        elif pre == "nse" and rest in nse:
            add(eid, "parent", nse[rest], "source_record", 1.0, f"NSE filing {rest}")
        elif pre == "ct" and rest in trials:
            p, m = trials[rest]
            add(eid, "parent", p, "source_record", 0.95, f"trial {rest} sponsor")
            for x in set((m or "").split(",")) | hl.get(("trials", rest), set()):
                add(eid, "molecule", x.strip(), "source_record", 0.95, f"trial {rest} interventions")
        elif pre == "fda" and rest in fda:
            add(eid, "parent", fda[rest], "source_record", 0.95, f"US FDA {rest} firm's group")
            for x in hl.get(("usfda_actions", rest), set()):
                add(eid, "molecule", x, "source_record", 0.95, f"US FDA {rest} product description")
        elif pre == "ja":
            code = rest.split("|")[1] if rest.count("|") >= 1 else ""
            for x in (ja.get(code) or "").split(","):
                add(eid, "molecule", x.strip(), "source_record", 0.9, f"Jan Aushadhi item {code}")
        elif pre in ("results", "resdue", "move"):
            t = rest.split("|")[0].replace(".NS", "")
            add(eid, "parent", tick.get(t), "source_record", 1.0, f"ticker {t}")
        for mid, method, conf, evid in found:
            add(eid, "molecule", mid, f"product_text_{method}", conf, evid)
        # the whole ingredient set, only when the text resolved completely and agrees with any payload ids
        if found and all(f[1] == "complete" and f[2] >= HIGH for f in found):
            s = {str(f[0]) for f in found}
            if not pl_mols or pl_mols <= s:     # extra connector ids (maybe a real active we missed): no set link
                add(eid, "ingredient_set", ",".join(sorted(s, key=int)), "product_text_complete_set", 0.9,
                    f"all ingredients resolved from “{seg[:120]}”")
    df = pd.DataFrame(rows)
    if len(df):
        df = df.sort_values("confidence", ascending=False).drop_duplicates(["event_id", "entity_type", "entity_id"])
        # a linked company's group, at the company link's confidence
        comp = df[df.entity_type == "company"]
        extra = [{"event_id": r.event_id, "entity_type": "parent", "entity_id": str(group_of[int(r.entity_id)]), "method": "company_group",
                  "confidence": r.confidence, "evidence": f"company {r.entity_id}'s group", "licence": lic}
                 for r in comp.itertuples() if int(r.entity_id) in group_of]
        if extra:
            df = pd.concat([df, pd.DataFrame(extra)]).sort_values("confidence", ascending=False).drop_duplicates(["event_id", "entity_type", "entity_id"])
    with db.writer() as w:
        w.execute("DELETE FROM event_entities")
        if len(df):
            w.register("_e", df)
            w.execute("INSERT INTO event_entities SELECT event_id, entity_type, entity_id, method, confidence, evidence, licence FROM _e")
            w.unregister("_e")
        high = int((df.confidence >= HIGH).sum()) if len(df) else 0
        w.execute("INSERT INTO linker_runs VALUES ('events', now(), now(), ?, ?, '')", [len(df), high])
    return {"linker": "events", "links": len(df), "high": high}
