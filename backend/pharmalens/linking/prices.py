"""Roadmap #11: pack-aware unit prices for every price observation (price_unit_obs); price_observations is untouched.

Each observation gets the pack its MRP was quoted for, from the best evidence available:
  source_row    the source's own pack for that product (data/derived/price_packs.parquet, from the raw 2022-24 and
                2025 catalogs) and the source's MRP equals the observation (0.95)
  mfr_list      the manufacturer's price list line (its own MRP and pack): unit price = list MRP / list pack (0.95)
  product_pack  only the catalog's current pack is known, so the pack is assumed (0.6, never comparable)

A point is `comparable` (safe on a per-unit trend line) when its pack is known from its own source, the unit kind
(tablet, ml, g...) matches the product's other comparable points, and its unit price is within 2.5x of their
median; anything else keeps its row with the reason in `note`.
"""
import statistics

import pandas as pd

from .. import db
from ..config import DATA_DIR
from ..normalize import pack_quantity
from .store import HIGH, ensure, licence_of

PACKS = DATA_DIR / "derived" / "price_packs.parquet"
MAX_RATIO = 2.5


def run() -> dict:
    ensure()
    cur = db.cursor()
    obs = cur.execute("""SELECT o.product_id, o.observed_on, o.source, o.mrp, p.name_norm, p.pack_size, p.pack_qty
                         FROM price_observations o JOIN products p ON p.id = o.product_id WHERE o.mrp > 0""").fetchall()
    src_pack: dict[tuple[str, str], tuple] = {}
    if PACKS.exists():
        for r in pd.read_parquet(PACKS).itertuples(index=False):
            unit = r.pack_unit if isinstance(r.pack_unit, str) else None      # parquet gives NaN for a missing unit
            src_pack[(r.name_norm, r.source)] = (r.pack_text, r.pack_qty if r.pack_qty == r.pack_qty else None, unit,
                                                 r.mrp if r.mrp == r.mrp else None)
    mfr = {}
    for pid, eff, mrp, pack, qty in cur.execute("""SELECT product_id, effective_on, mrp, pack, pack_qty FROM mfr_prices
                                                   WHERE product_id IS NOT NULL AND mrp > 0""").fetchall():
        mfr[(pid, eff)] = (mrp, pack, qty)
    lic_cat, lic_mfr = licence_of("price_observations", "products"), licence_of("mfr_prices")

    rows = []
    for pid, d, src, mrp, nn, cur_pack, cur_qty in obs:
        rec = {"product_id": pid, "observed_on": d, "source": src, "mrp": mrp, "pack_text": None, "pack_qty": None,
               "pack_basis": None, "unit_price": None, "comparable": False, "method": None, "confidence": 0.0, "note": "",
               "licence": lic_cat, "_unit": None}
        sp = src_pack.get((nn, src))
        if src.startswith("mfr:") and (pid, d) in mfr:
            lmrp, lpack, lqty = mfr[(pid, d)]
            if lqty:
                rec.update(pack_text=lpack, pack_qty=lqty, pack_basis="mfr_list", unit_price=lmrp / lqty, method="mfr_list_unit",
                           confidence=0.95, licence=lic_mfr, _unit=pack_quantity(f"pack of {lqty:g} {lpack or ''}")[1])
        elif sp and sp[1] and sp[3] and abs(sp[3] - mrp) <= max(0.5, 0.01 * mrp):
            rec.update(pack_text=sp[0], pack_qty=sp[1], pack_basis="source_row", unit_price=mrp / sp[1], method="source_pack",
                       confidence=0.95, _unit=sp[2])
        if rec["pack_basis"] is None and cur_qty:
            rec.update(pack_text=cur_pack, pack_qty=cur_qty, pack_basis="product_pack", unit_price=mrp / cur_qty, method="assumed_current_pack",
                       confidence=0.6, note="pack not known for this source: the catalog's current pack is assumed")
            rec["_unit"] = pack_quantity(cur_pack)[1]
        if rec["pack_basis"] is None:
            rec.update(method="no_pack", note="no pack known")
        rows.append(rec)

    # comparability within each product
    by: dict[int, list[dict]] = {}
    for r in rows:
        by.setdefault(r["product_id"], []).append(r)
    for pts in by.values():
        known = [r for r in pts if r["confidence"] >= HIGH and r["unit_price"]]
        if not known:
            continue
        units = {r["_unit"] for r in known if r["_unit"]}
        main_unit = max(units, key=lambda u: sum(1 for r in known if r["_unit"] == u)) if units else None
        med = statistics.median(r["unit_price"] for r in known)
        for r in known:
            if main_unit and r["_unit"] and r["_unit"] != main_unit:
                r["note"] = f"pack counted in {r['_unit']}, other points in {main_unit}"
            elif max(r["unit_price"], med) / min(r["unit_price"], med) > MAX_RATIO:
                r["note"] = f"unit price {r['unit_price'] / med:.1f}x the product's median: pack or unit mismatch likely"
            else:
                r["comparable"] = True
    df = pd.DataFrame(rows).drop(columns=["_unit"])
    with db.writer() as w:
        w.execute("DELETE FROM price_unit_obs")
        w.register("_p", df)
        w.execute("""INSERT INTO price_unit_obs SELECT product_id::INTEGER, observed_on::DATE, source, mrp, pack_text, pack_qty::DOUBLE, pack_basis,
                     unit_price::DOUBLE, comparable, method, confidence, note, licence FROM _p""")
        w.unregister("_p")
        high = int((df.confidence >= HIGH).sum())
        w.execute("INSERT INTO linker_runs VALUES ('prices', now(), now(), ?, ?, ?)",
                  [len(df), high, f"{int(df.comparable.sum()):,} comparable; packs file {'found' if PACKS.exists() else 'missing'}"])
    return {"linker": "prices", "links": len(df), "high": high, "comparable": int(df.comparable.sum())}
