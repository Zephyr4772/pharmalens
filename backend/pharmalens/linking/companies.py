"""Roadmap #3: company resolver and auto-groups.

Curated groups (parents, group_kind = 'curated') are untouched and companies.parent_id is never written. Every company
outside a curated group gets an auto-group (auto_groups, group_kind = 'auto'), linked by entity_links
(company -> auto_group):
  singleton        the company is its own group (1.0)
  name_variant     companies whose strict firm key is equal and distinctive ("Aspen Pharma" / "Aspen
                   Pharmaceuticals Pvt Ltd") share one auto-group (0.85)
The strict key drops legal words and folds spelling synonyms (pharmaceuticals = pharma, laboratories = labs) but keeps
initials ("S P Pharma" != "M M Pharma") and an "India" inside the name ("Heal India Pharma" != "Heal Pharma"). A key
made only of generic words and initials is not distinctive: those companies stay singletons. Names that match only
with spaces removed ("Doc Med" / "Docmed") get an inferred possible_alias link between the two companies (0.7).

Also resolves CDSCO approval applicants to catalog companies (exact firm key, matcher.company_for; 0.9).
"""
import re
from collections import defaultdict

import pandas as pd

from .. import db, matcher
from ..normalize import norm
from .store import ensure, licence_of, replace

LEGAL = {"pvt", "private", "ltd", "limited", "llp", "inc", "co", "corp", "corporation", "company", "the", "ms", "and"}
GENERIC = {"pharma", "labs", "healthcare", "lifesciences", "formulations", "remedies", "biotech", "biotec", "medicare",
           "medicals", "medical", "drugs", "chemicals", "biologicals", "biosciences", "sciences", "health", "life", "care",
           "products", "industries", "international", "global", "india", "organics", "therapeutics", "biocare", "bio",
           "generics", "exports", "impex", "enterprises", "group", "medicines", "pharmacia", "wellness", "nutrition",
           "cure", "med", "herbal", "ayurveda", "research", "pvt", "new", "and"}
SYN = matcher.FIRM_SYNONYM

DDL = """
CREATE TABLE IF NOT EXISTS auto_groups (     -- one per company outside a curated group (or per set of name variants)
    group_key   VARCHAR PRIMARY KEY,         -- 'auto:<strict firm key>' or 'auto:c<company id>'
    name        VARCHAR,                     -- the member with the most active SKUs
    members     INTEGER,
    active_skus INTEGER,
    group_kind  VARCHAR,                     -- always 'auto' (curated groups live in parents)
    created_at  TIMESTAMP
);
ALTER TABLE parents ADD COLUMN IF NOT EXISTS group_kind VARCHAR DEFAULT 'curated';
"""


def strict_key(name: str) -> str:
    s = matcher._firm_text(name or "")
    s = re.sub(r"\(\s*india\s*\)", " ", s)                        # "(India)" is a registration detail
    toks = s.replace("life sciences", "lifesciences").replace("life science", "lifesciences").replace("health care", "healthcare").split()
    while toks and toks[-1] in LEGAL | {"india"}:                 # "... India Pvt Ltd": trailing India goes
        toks.pop()
    toks = [SYN.get(t, t) for t in toks if t not in LEGAL]
    while toks and toks[-1] == "india":
        toks.pop()
    return " ".join(toks)


def distinctive(key: str) -> bool:
    return any(len(t) >= 3 and t not in GENERIC for t in key.split())


def run() -> list[dict]:
    ensure()
    with db.writer() as w:
        w.execute(DDL)
    cur = db.cursor()
    matcher._load()
    comps = cur.execute("SELECT id, name, coalesce(active_count, 0) FROM companies WHERE parent_id IS NULL").fetchall()
    by_key: dict[str, list] = defaultdict(list)
    for cid, name, ac in comps:
        by_key[strict_key(name)].append((cid, name, ac))
    lic = licence_of("companies")
    links, groups = [], []
    for key, members in by_key.items():
        if len(members) > 1 and key and distinctive(key):
            gk = f"auto:{key}"
            lead = max(members, key=lambda m: m[2])
            groups.append({"group_key": gk, "name": lead[1], "members": len(members), "active_skus": sum(m[2] for m in members)})
            for cid, name, _ in members:
                links.append({"src_table": "companies", "src_key": cid, "dst_type": "auto_group", "dst_id": gk, "method": "name_variant",
                              "confidence": 0.85, "evidence": f"'{name}' -> firm key '{key}' (shared by {len(members)} companies)", "licence": lic})
        else:
            for cid, name, ac in members:
                gk = f"auto:c{cid}"
                groups.append({"group_key": gk, "name": name, "members": 1, "active_skus": ac})
                note = "" if len(norm(name).replace(" ", "")) >= 4 else " (name looks truncated: check the source rows)"
                links.append({"src_table": "companies", "src_key": cid, "dst_type": "auto_group", "dst_id": gk, "method": "singleton",
                              "confidence": 1.0, "evidence": f"'{name}' is its own group{note}", "licence": lic})
    # spacing-only variants: inferred, never merged
    by_sq: dict[str, list] = defaultdict(list)
    for cid, name, ac in comps:
        q = matcher.firm_squash(name)
        if len(q) >= 8:
            by_sq[q].append((cid, name, strict_key(name)))
    for q, ms in by_sq.items():
        if len({m[2] for m in ms}) > 1:
            for a in ms:
                for b in ms:
                    if a[0] != b[0] and a[2] != b[2]:
                        links.append({"src_table": "companies", "src_key": a[0], "dst_type": "company", "dst_id": b[0], "method": "possible_alias",
                                      "confidence": 0.7, "evidence": f"'{a[1]}' and '{b[1]}' match with spaces removed ('{q}')", "licence": lic})
    gdf = pd.DataFrame(groups).drop_duplicates("group_key")
    gdf["group_kind"], gdf["created_at"] = "auto", pd.Timestamp.now()
    with db.writer() as w:
        w.execute("DELETE FROM auto_groups")
        w.register("_g", gdf)
        w.execute("INSERT INTO auto_groups SELECT group_key, name, members::INTEGER, active_skus::INTEGER, group_kind, created_at FROM _g")
        w.unregister("_g")
    # approval applicants -> companies (exact firm key only)
    lic_a = licence_of("reg_approvals", "companies")
    appr = []
    cache: dict[str, int | None] = {}
    for aid, applicant in cur.execute("SELECT id, applicant FROM reg_approvals WHERE applicant IS NOT NULL").fetchall():
        if applicant not in cache:
            cache[applicant] = matcher.company_for(applicant)
        if cache[applicant]:
            appr.append({"src_table": "reg_approvals", "src_key": aid, "dst_type": "company", "dst_id": cache[applicant],
                         "method": "firm_key_exact", "confidence": 0.9, "evidence": f"applicant '{applicant}' = catalog company key", "licence": lic_a})
    return [replace("company:auto_groups", links, note=f"{len(gdf):,} auto-groups"), replace("company:approvals", appr)]
