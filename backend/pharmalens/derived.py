"""Derived analytics recomputed after core builds and whenever connectors add data.

Market-share estimate (no paid sales data — see docs/METHODOLOGY.md):

    weight(sku) = sqrt(MRP_per_pack) x availability x reach
      availability = 1.0 in stock on an e-pharmacy in the latest scrape
                     0.6 status unknown
                     0.25 listed out of stock, 0.0 discontinued
      reach        = 1 + ln(1 + number of independent catalogues/pharmacies listing the SKU)

    value_share(owner, segment)   = sum(weight) of owner's SKUs / sum(weight) in segment
    breadth_share(owner, segment) = owner's active SKUs / active SKUs in segment
    owner = parent group when mapped (Sun Pharma incl. Ranbaxy, Sun Pharma Labs, ...), else the company.

HHI on value shares (0-10,000) gives segment concentration.
"""
import logging
import time

from . import db

log = logging.getLogger("pharmalens.derived")

# sqrt(MRP): pure MRP weighting let a handful of lakh-rupee oncology biologics outrank Sun/Cipla;
# square-root dampening reproduces the published IPM ordering of the top groups much more closely.
WEIGHT_SQL = """
    sqrt(p.mrp)
    * CASE WHEN coalesce(p.is_discontinued, false) THEN 0.0
           WHEN p.in_stock IS TRUE THEN 1.0
           WHEN p.in_stock IS FALSE THEN 0.25
           ELSE 0.6 END
    * (1 + ln(1 + coalesce(p.source_count, 1)))
"""

OWNER_SQL = """
    CASE WHEN c.parent_id IS NOT NULL THEN 'parent' ELSE 'company' END AS owner_type,
    coalesce(c.parent_id, c.id) AS owner_id
"""


def refresh_combo_prices(cur):
    """Brand counts and MRP / per-unit spreads per combination (catalog build, and after a price feed updates MRPs)."""
    cur.execute("""
        UPDATE combos SET
          product_count = s.pc, company_count = s.cc, min_mrp = s.mn, median_mrp = s.md, max_mrp = s.mx,
          therapeutic_class = s.tc
        FROM (SELECT combo_id, count(*) pc, count(DISTINCT company_id) cc,
                     min(mrp) mn, median(mrp) md, max(mrp) mx, mode(therapeutic_class) tc
              FROM products WHERE combo_id IS NOT NULL GROUP BY 1) s
        WHERE combos.id = s.combo_id""")
    cur.execute("""
        UPDATE combos SET min_unit = s.mn, median_unit = s.md, max_unit = s.mx
        FROM (SELECT p.combo_id, min(p.unit_price) mn, median(p.unit_price) md, max(p.unit_price) mx
              FROM products p
              JOIN (SELECT combo_id, median(unit_price) med FROM products WHERE unit_price > 0 GROUP BY 1) m USING (combo_id)
              WHERE p.unit_price >= 0.15 * m.med AND p.unit_price <= 20 * m.med
              GROUP BY 1) s
        WHERE combos.id = s.combo_id""")


def refresh_market_share(cur):
    t0 = time.time()
    cur.execute("DROP TABLE IF EXISTS segment_share")
    cur.execute(f"""
        CREATE TABLE segment_share AS
        WITH base AS (
            SELECT p.id pid, p.therapeutic_class, p.combo_id, {OWNER_SQL},
                   {WEIGHT_SQL} AS w,
                   CASE WHEN coalesce(p.is_discontinued, false) THEN 0 ELSE 1 END AS active
            FROM products p JOIN companies c ON c.id = p.company_id
            WHERE p.mrp IS NOT NULL AND p.mrp > 0
        ),
        seg AS (
            SELECT 'class' AS segment_type, therapeutic_class AS segment, owner_type, owner_id, w, active FROM base WHERE therapeutic_class IS NOT NULL
            UNION ALL
            SELECT 'combo', CAST(combo_id AS VARCHAR), owner_type, owner_id, w, active FROM base WHERE combo_id IS NOT NULL
            UNION ALL
            SELECT 'molecule', CAST(pm.molecule_id AS VARCHAR), owner_type, owner_id, w, active
            FROM base JOIN product_molecules pm ON pm.product_id = base.pid
        ),
        agg AS (
            SELECT segment_type, segment, owner_type, owner_id, sum(active) AS skus, sum(w) AS w
            FROM seg GROUP BY ALL
        )
        SELECT *,
               w / nullif(sum(w) OVER (PARTITION BY segment_type, segment), 0) AS value_share,
               skus / nullif(sum(skus) OVER (PARTITION BY segment_type, segment), 0) AS breadth_share,
               row_number() OVER (PARTITION BY segment_type, segment ORDER BY w DESC) AS rank
        FROM agg
    """)
    cur.execute("DROP TABLE IF EXISTS segment_stats")
    cur.execute("""
        CREATE TABLE segment_stats AS
        SELECT segment_type, segment, count(*) AS owners, sum(skus) AS skus,
               round(sum(power(value_share * 100, 2))) AS hhi,
               max(value_share) FILTER (WHERE rank = 1) AS leader_share,
               max(owner_type || ':' || owner_id) FILTER (WHERE rank = 1) AS leader
        FROM segment_share GROUP BY 1, 2
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_share_seg ON segment_share(segment_type, segment)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_share_owner ON segment_share(owner_type, owner_id)")
    log.info("market share refreshed in %.1fs", time.time() - t0)


QUALIFIERS = {
    # qualifier in ban text -> words that must appear in the product name / form / pack
    "injection": ("injection", "inj", "infusion", "vial", "ampoule"),
    "suspension": ("suspension", "susp"),
    "syrup": ("syrup", "linctus", "liquid", "oral solution", "elixir"),
    "dispersible": ("dispersible", " dt", "dt "),
    "modified_release": (" sr", "sr ", " er", "er ", " xr", " cr", " mr", "sustained", "extended", "controlled", "prolonged", " od"),
    "drops": ("drop",),
    "gel": ("gel",), "cream": ("cream",), "ointment": ("ointment",), "lotion": ("lotion",),
    "powder": ("powder", "sachet", "granules"),
    "inhalation": ("inhal", "respule", "rotacap", "inhaler"),
    "capsule": ("capsule",), "tablet": ("tablet",),
}
BAN_QUALIFIER_RX = {
    "injection": r"\binj", "suspension": r"suspension", "syrup": r"syrup|linctus|oral liquid|elixir",
    "dispersible": r"dispersible|\bdt\b", "modified_release": r"\(sr\)|\bsr\b|sustained|extended release|\ber\b|\bcr\b|controlled release|modified release",
    "drops": r"\bdrops?\b", "gel": r"\bgel\b", "cream": r"\bcream\b", "ointment": r"ointment", "lotion": r"lotion",
    "powder": r"powder|sachet|granules", "inhalation": r"inhal|respule|rotacap",
    "capsule": r"capsule", "tablet": r"tablet",
}
STRENGTH_TOKEN = r"(\d+(?:\.\d+)?)\s*(mcg|mg|g|gm|ml|iu|%)"


def _ban_spec(text: str) -> tuple[dict, set]:
    """Per-molecule allowed strengths and the dosage-form qualifiers named in the ban text."""
    import re
    from .normalize import molecule_key, norm_strength
    low = text.lower()
    quals = {q for q, rx in BAN_QUALIFIER_RX.items() if re.search(rx, low)}
    if quals & {"dispersible", "modified_release"}:
        quals -= {"tablet", "capsule"}  # 'dispersible tablets' only needs the dispersible check
    strengths: dict[str, set] = {}
    for part in text.split("+"):
        found = re.findall(STRENGTH_TOKEN, part, re.I)
        name = re.sub(STRENGTH_TOKEN, " ", part, flags=re.I)
        name = re.sub(r"\(.*?\)|\b(ip|bp|usp|tablets?|capsules?|syrup|suspension|injection|dispersible)\b|[/,]", " ", name, flags=re.I)
        k = molecule_key(name)
        if k and found:
            strengths[k] = {norm_strength(n + u) for n, u in found}
    return strengths, quals


def refresh_bans(cur):
    """Match prohibited FDCs to catalog products, respecting strengths and dosage forms named in the
    notification. ban_level: 'exact' = every stated constraint verified; 'review' = molecules match but
    the product lacks the strength/form detail needed to confirm."""
    from .normalize import norm
    cur.execute("UPDATE products SET ban_level = NULL, ban_id = NULL WHERE ban_level IS NOT NULL")
    cur.execute("UPDATE combos SET is_banned = false WHERE is_banned")
    bans = cur.execute("SELECT id, combo_text, mkey FROM reg_banned_fdc WHERE status = 'banned' AND mkey IS NOT NULL").fetchall()
    hits: dict[int, tuple[str, int]] = {}
    for ban_id, text, mkey in bans:
        strengths, quals = _ban_spec(text)
        prods = cur.execute("""
            SELECT p.id, p.name_norm, lower(coalesce(p.dosage_form, '')), lower(coalesce(p.pack_size, '')), k.ckey
            FROM products p JOIN combos k ON k.id = p.combo_id WHERE k.mkey = ?""", [mkey]).fetchall()
        for pid, name, form, pack, ckey in prods:
            level = "exact"
            text_p = f" {name} {norm(form)} {norm(pack)} "
            for q in quals:
                if not any(w in text_p for w in QUALIFIERS[q]):
                    level = None
                    break
            if level is None:
                continue
            prod_str = dict(x.split(":", 1) for x in ckey.split("#", 1)[0].split("|"))
            for mol, allowed in strengths.items():
                s = prod_str.get(mol, "")
                if not s:
                    level = "review"
                elif s not in allowed:
                    level = None
                    break
            if level is None:
                continue
            if level == "exact" and text.count("+") + 1 > len(mkey.split("|")):
                level = "review"
            prev = hits.get(pid)
            if not prev or (prev[0] == "review" and level == "exact"):
                hits[pid] = (level, ban_id)
    if hits:
        import pandas as pd
        df = pd.DataFrame([(pid, lv, bid) for pid, (lv, bid) in hits.items()], columns=["pid", "lvl", "bid"])
        cur.register("_bans", df)
        cur.execute("UPDATE products SET ban_level = _bans.lvl, ban_id = _bans.bid FROM _bans WHERE products.id = _bans.pid")
        cur.unregister("_bans")
    # a combo is 'banned' only when every product in it is an exact match (bans are often form-specific)
    cur.execute("UPDATE combos SET banned_skus = 0")
    cur.execute("""UPDATE combos SET banned_skus = s.n, is_banned = (s.n = combos.product_count)
                   FROM (SELECT combo_id, count(*) n FROM products WHERE ban_level = 'exact' GROUP BY 1) s
                   WHERE combos.id = s.combo_id""")
    log.info("bans: %d products exact, %d review", sum(1 for v in hits.values() if v[0] == "exact"),
             sum(1 for v in hits.values() if v[0] == "review"))


MIGRATIONS = [
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS ban_level VARCHAR",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS ban_id BIGINT",
    "ALTER TABLE combos ADD COLUMN IF NOT EXISTS banned_skus INTEGER",
    "ALTER TABLE reg_approvals ADD COLUMN IF NOT EXISTS composition VARCHAR",
    "ALTER TABLE reg_approvals ADD COLUMN IF NOT EXISTS dosage_form VARCHAR",
    "ALTER TABLE reg_approvals ADD COLUMN IF NOT EXISTS sites JSON",
    "ALTER TABLE reg_approvals ADD COLUMN IF NOT EXISTS division VARCHAR",
    "ALTER TABLE reg_approvals ADD COLUMN IF NOT EXISTS applied_for VARCHAR",
    "ALTER TABLE reg_approvals ADD COLUMN IF NOT EXISTS form_id BIGINT",
]


def migrate():
    """Additive column migrations; DuckDB needs DDL outside the refresh transaction."""
    with db.WRITE_LOCK:
        cur = db.cursor()
        for sql in MIGRATIONS:
            cur.execute(sql)
        # DuckDB 1.5 cannot replay ALTER TABLE from the WAL ("GetDefaultDatabase" internal error),
        # so make the schema change durable in the main file immediately.
        try:
            cur.execute("CHECKPOINT")
        except Exception:  # noqa: BLE001 — another write is open; the next connector run checkpoints
            log.warning("migrate: checkpoint deferred (write in progress)")


def refresh_reference(cur):
    """Molecule flags that depend on live regulatory tables."""
    cur.execute("UPDATE molecules SET is_nlem = (id IN (SELECT molecule_id FROM nlem WHERE molecule_id IS NOT NULL))")
    cur.execute("UPDATE molecules SET nppa_ceiling = NULL WHERE nppa_ceiling IS NOT NULL")
    cur.execute("""UPDATE molecules SET nppa_ceiling = s.cp
                   FROM (SELECT molecule_id, min(ceiling_price) cp FROM nppa_ceiling WHERE molecule_id IS NOT NULL GROUP BY 1) s
                   WHERE molecules.id = s.molecule_id""")


def refresh_derived():
    # schema migrations run once at server start (api lifespan / CLI), not after every feed
    with db.writer() as cur:
        refresh_reference(cur)
        refresh_bans(cur)
        refresh_market_share(cur)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    refresh_derived()
