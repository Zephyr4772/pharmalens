"""Roadmap #5: launch dating. Dated signals that a company brought a given ingredient set to market (launch_signals),
and company links for new-brand sightings.

Signals (one row each, never merged into a single "launch date" so the evidence stays visible):
  registry_arrival   a brand first seen in the CDSCO 84AB brand registry after monitoring began (date = the weekly
                     snapshot it first appeared in)                                            0.95
  nppa_launch_price  NPPA fixed the retail price of a new drug formulation for this company (Gazette S.O.; a price
                     is fixed before launch, so this dates the launch to within weeks)            0.9
  cdci_record_date   the brand's record date in CDCI after the initial bulk load (added or last updated, so a
                     "listed by" date, not a launch date)                                         0.7, inferred
The ingredient set is attached only when the generic text resolved completely (same resolver as #4); the company only
by an exact firm-name key match (matcher.company_for: no prefix or fuzzy guessing).
"""
import pandas as pd

from .. import db, matcher
from .molecules import _index, resolve
from .store import HIGH, ensure, licence_of, replace

CDCI_BULK = "2024-04-18"     # CDCI's first load: everything present then has no meaningful date

DDL = """
CREATE TABLE IF NOT EXISTS launch_signals (
    kind           VARCHAR,     -- registry_arrival | nppa_launch_price | cdci_record_date
    dated_on       DATE,
    company_id     INTEGER,
    ingredient_set VARCHAR,     -- sorted molecule ids, only when completely resolved
    brand          VARCHAR,
    src_table      VARCHAR,
    src_key        VARCHAR,
    method         VARCHAR,
    confidence     DOUBLE,
    evidence       VARCHAR,
    licence        VARCHAR
);
"""


def _set(text, idx):
    found = resolve(text or "", True, idx)
    if found and all(f[1] == "complete" and f[2] >= HIGH for f in found):
        return ",".join(sorted({str(f[0]) for f in found}, key=int))
    return None


def run() -> list[dict]:
    ensure()
    with db.writer() as w:
        w.execute(DDL)
    cur = db.cursor()
    idx = _index()
    matcher._load()
    firm_cache: dict[str, int | None] = {}

    def company(firm):
        if firm not in firm_cache:
            firm_cache[firm] = matcher.company_for(firm)
        return firm_cache[firm]

    # CDCI brands carry their own ingredient structure: brand -> generic -> substances -> molecules
    cdci_set = {}
    for bid, subs in cur.execute("""SELECT b.identifier, g.substance_identifier FROM cdci_brand b
                                    JOIN cdci_generic g ON g.identifier = b.generic_identifier""").fetchall():
        cdci_set[str(bid)] = subs
    sub_mol = {str(i): int(m) for i, m in cur.execute("SELECT identifier, molecule_id FROM cdci_substance").fetchall() if m is not None}

    def cdci_ingredients(bid):
        subs = [x for x in (cdci_set.get(bid) or "").split("+") if x]
        mols = [sub_mol.get(x) for x in subs]
        if not subs or any(m is None for m in mols):
            return None        # a substance we cannot map: the set is not known exactly
        return ",".join(sorted({str(m) for m in mols}, key=int))

    # company links for new-brand sightings
    lic_b = licence_of("brand_first_seen", "companies")
    clinks, sig = [], []
    rows = cur.execute("SELECT source, key, brand, firm, generic, company_id, first_seen, baseline FROM brand_first_seen").fetchall()
    for src, key, brand, firm, generic, cid, seen, base in rows:
        sk = f"{src}|{key}"
        c = cid or company(firm)
        if cid:
            clinks.append({"src_table": "brand_first_seen", "src_key": sk, "dst_type": "company", "dst_id": cid, "method": "source_column",
                           "confidence": 1.0, "evidence": f"firm '{firm}'", "licence": lic_b})
        elif c:
            clinks.append({"src_table": "brand_first_seen", "src_key": sk, "dst_type": "company", "dst_id": c, "method": "firm_key_exact",
                           "confidence": 0.9, "evidence": f"firm '{firm}' = catalog company key", "licence": lic_b})
        dated = (src == "cdsco_84ab" and not base) or (src == "cdci" and seen and str(seen) > CDCI_BULK)
        if dated:
            kind, conf = ("registry_arrival", 0.95) if src == "cdsco_84ab" else ("cdci_record_date", 0.7)
            iset = cdci_ingredients(key) if src == "cdci" else _set(generic, idx)
            sig.append({"kind": kind, "dated_on": seen, "company_id": c, "ingredient_set": iset, "brand": brand,
                        "src_table": "brand_first_seen", "src_key": sk, "method": kind, "confidence": conf,
                        "evidence": f"{brand} ({generic}) by {firm}, first seen {seen}", "licence": lic_b})
    lic_n = licence_of("nppa_retail_prices", "companies")
    for key, d, form, strength, mfr, mkt, cid in cur.execute("""SELECT key, notified_on, formulation, strength, manufacturer, marketer, company_id
                                                                FROM nppa_retail_prices WHERE notified_on IS NOT NULL""").fetchall():
        c = cid or company(mkt) or company(mfr)
        sig.append({"kind": "nppa_launch_price", "dated_on": d, "company_id": c, "ingredient_set": _set(form, idx), "brand": None,
                    "src_table": "nppa_retail_prices", "src_key": key, "method": "nppa_launch_price", "confidence": 0.9,
                    "evidence": f"NPPA retail price for {form} {strength or ''} ({mkt or mfr}), notified {d}", "licence": lic_n})
    df = pd.DataFrame(sig)
    with db.writer() as w:
        w.execute("DELETE FROM launch_signals")
        if len(df):
            w.register("_s", df)
            w.execute("""INSERT INTO launch_signals SELECT kind, dated_on::DATE, company_id::INTEGER, ingredient_set, brand, src_table, src_key,
                         method, confidence, evidence, licence FROM _s""")
            w.unregister("_s")
    high = int((df.confidence >= HIGH).sum()) if len(df) else 0
    return [replace("launch:brand_company", clinks),
            {"linker": "launch:signals", "links": len(df), "high": high,
             "with_set": int(df.ingredient_set.notna().sum()) if len(df) else 0, "with_company": int(df.company_id.notna().sum()) if len(df) else 0}]
