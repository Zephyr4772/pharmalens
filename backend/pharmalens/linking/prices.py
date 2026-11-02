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
from .. import db
from ..config import DATA_DIR
from .store import HIGH, ensure, licence_of

PACKS = DATA_DIR / "derived" / "price_packs.parquet"
MAX_RATIO = 2.5
UNIT_RX = r"(tablet|capsule|softgel|ml|gm|g|sachet|unit|piece|lozenge|injection|patch|respule|rotacap|suppositor|pessar|strip|vial|ampoule)"


def run() -> dict:
    """All in one DuckDB statement: ~650k observations stay inside the database's memory cap (the server has 2 GB)."""
    ensure()
    packs = str(PACKS).replace("\\", "/").replace("'", "''")
    sp = (f"SELECT name_norm, source, pack_text, pack_qty, NULLIF(pack_unit, '') pack_unit, mrp smrp FROM read_parquet('{packs}')"
          if PACKS.exists() else
          "SELECT NULL::VARCHAR name_norm, NULL::VARCHAR source, NULL::VARCHAR pack_text, NULL::DOUBLE pack_qty, NULL::VARCHAR pack_unit, NULL::DOUBLE smrp WHERE false")
    lic_cat, lic_mfr = licence_of("price_observations", "products"), licence_of("mfr_prices")
    with db.writer() as w:
        w.execute("DELETE FROM price_unit_obs")
        w.execute(f"""
        INSERT INTO price_unit_obs
        WITH sp AS ({sp}),
        mf AS (SELECT product_id, effective_on, any_value(mrp) lmrp, any_value(pack) lpack, any_value(pack_qty) lqty
               FROM mfr_prices WHERE product_id IS NOT NULL AND mrp > 0 GROUP BY 1, 2),
        o AS (SELECT o.product_id, o.observed_on, o.source, o.mrp, p.name_norm, p.pack_size, p.pack_qty cur_qty
              FROM price_observations o JOIN products p ON p.id = o.product_id WHERE o.mrp > 0),
        j AS (SELECT o.*, sp.pack_text sp_text, sp.pack_qty sp_qty, sp.pack_unit sp_unit, sp.smrp, mf.lmrp, mf.lpack, mf.lqty
              FROM o LEFT JOIN sp ON sp.name_norm = o.name_norm AND sp.source = o.source
              LEFT JOIN mf ON o.source LIKE 'mfr:%' AND mf.product_id = o.product_id AND mf.effective_on = o.observed_on),
        b AS (SELECT *, CASE WHEN lqty > 0 THEN 'mfr_list'
                             WHEN sp_qty > 0 AND smrp IS NOT NULL AND abs(smrp - mrp) <= greatest(0.5, 0.01 * mrp) THEN 'source_row'
                             WHEN cur_qty > 0 THEN 'product_pack' END AS basis FROM j),
        u AS (SELECT product_id, observed_on, source, mrp, basis,
                     CASE basis WHEN 'mfr_list' THEN lpack WHEN 'source_row' THEN sp_text WHEN 'product_pack' THEN pack_size END AS pack_text,
                     CASE basis WHEN 'mfr_list' THEN lqty WHEN 'source_row' THEN sp_qty WHEN 'product_pack' THEN cur_qty END AS pack_qty,
                     CASE basis WHEN 'mfr_list' THEN lmrp / lqty WHEN 'source_row' THEN mrp / sp_qty WHEN 'product_pack' THEN mrp / cur_qty END AS unit_price,
                     CASE basis WHEN 'mfr_list' THEN NULLIF(regexp_extract(lower(coalesce(lpack, '')), '{UNIT_RX}', 1), '')
                                WHEN 'source_row' THEN sp_unit END AS unit,
                     CASE basis WHEN 'mfr_list' THEN 'mfr_list_unit' WHEN 'source_row' THEN 'source_pack'
                                WHEN 'product_pack' THEN 'assumed_current_pack' ELSE 'no_pack' END AS meth,
                     CASE basis WHEN 'mfr_list' THEN 0.95 WHEN 'source_row' THEN 0.95 WHEN 'product_pack' THEN 0.6 ELSE 0.0 END AS confidence,
                     CASE WHEN basis = 'mfr_list' THEN '{lic_mfr}' ELSE '{lic_cat}' END AS licence
              FROM b),
        st AS (SELECT product_id, median(unit_price) med, mode(unit) main_unit FROM u WHERE confidence >= {HIGH} AND unit_price > 0 GROUP BY 1)
        SELECT u.product_id, u.observed_on, u.source, u.mrp, u.pack_text, u.pack_qty, u.basis, u.unit_price,
               u.confidence >= {HIGH} AND u.unit_price > 0 AND NOT (u.unit IS NOT NULL AND st.main_unit IS NOT NULL AND u.unit <> st.main_unit)
                 AND greatest(u.unit_price, st.med) / least(u.unit_price, st.med) <= {MAX_RATIO} AS comparable,
               u.meth, u.confidence,
               CASE WHEN u.basis IS NULL THEN 'no pack known'
                    WHEN u.basis = 'product_pack' THEN 'pack not known for this source: the catalog''s current pack is assumed'
                    WHEN u.unit IS NOT NULL AND st.main_unit IS NOT NULL AND u.unit <> st.main_unit
                      THEN 'pack counted in ' || u.unit || ', other points in ' || st.main_unit
                    WHEN greatest(u.unit_price, st.med) / least(u.unit_price, st.med) > {MAX_RATIO}
                      THEN 'unit price ' || round(u.unit_price / st.med, 1) || 'x the product''s median: pack or unit mismatch likely'
                    ELSE '' END AS note,
               u.licence
        FROM u LEFT JOIN st USING (product_id)""")
        n, high, comp = w.execute(f"SELECT count(*), count(*) FILTER (WHERE confidence >= {HIGH}), count(*) FILTER (WHERE comparable) FROM price_unit_obs").fetchone()
        w.execute("INSERT INTO linker_runs VALUES ('prices', now(), now(), ?, ?, ?)",
                  [n, high, f"{comp:,} comparable; packs file {'found' if PACKS.exists() else 'missing'}"])
    return {"linker": "prices", "links": n, "high": high, "comparable": comp}
