"""Data depth audit: link coverage and the five end-to-end test paths (docs/data-depth-audit.md).

Read-only. Works on any copy of the database, with or without the Phase 1 link tables (they simply count as
empty), so the same script gives the "before" and "after" numbers.

    py -3 analysis/audit.py <path/to/pharmalens.duckdb> [--json out.json]

"Linked" means: the source table's own column OR a high-confidence derived link (confidence >= 0.85). Inferred
links (below 0.85) are reported separately and never counted as coverage.
"""
import json
import os
import sys
from datetime import datetime

import duckdb

HIGH = 0.85


def main(path: str, out: str | None = None) -> dict:
    c = duckdb.connect(path, read_only=True)
    c.execute(f"SET memory_limit='{os.getenv('AUDIT_MEMORY', '1500MB')}'")   # the server has 2 GB: AUDIT_MEMORY=400MB there
    tables = {r[0] for r in c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()}
    for t, ddl in [("entity_links", "linker VARCHAR, src_table VARCHAR, src_key VARCHAR, dst_type VARCHAR, dst_id VARCHAR, method VARCHAR, confidence DOUBLE"),
                   ("event_entities", "event_id BIGINT, entity_type VARCHAR, entity_id VARCHAR, method VARCHAR, confidence DOUBLE"),
                   ("price_unit_obs", "product_id INTEGER, observed_on DATE, source VARCHAR, unit_price DOUBLE, comparable BOOLEAN, confidence DOUBLE"),
                   ("launch_signals", "kind VARCHAR, dated_on DATE, company_id INTEGER, ingredient_set VARCHAR, confidence DOUBLE")]:
        if t not in tables:   # absent before Phase 1: an empty stand-in keeps every query valid
            c.execute(f"CREATE TEMP TABLE {t} ({ddl})")
    has_group_kind = "group_kind" in {r[0] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'parents'").fetchall()}

    def one(sql, *a):
        return c.execute(sql, list(a)).fetchone()

    def pct(k, n):
        return round(k / n * 100, 1) if n else None

    # high-confidence molecule links per record, as a sorted set (string) for set comparisons
    c.execute(f"""CREATE TEMP VIEW hl AS SELECT * FROM entity_links WHERE confidence >= {HIGH}""")
    # ingredient sets only from records whose whole set was resolved (no 'partial' link): set comparisons need that
    c.execute("""CREATE TEMP VIEW molset AS SELECT src_table, src_key, string_agg(dst_id, ',' ORDER BY CAST(dst_id AS INTEGER)) s
                 FROM hl WHERE dst_type = 'molecule' GROUP BY 1, 2
                 HAVING count(*) FILTER (WHERE method LIKE '%partial%') = 0""")
    c.execute("""CREATE TEMP MACRO sortset(ids) AS (SELECT string_agg(m, ',' ORDER BY CAST(m AS INTEGER))
                 FROM (SELECT DISTINCT trim(x) m FROM unnest(string_split(ids, ',')) t(x) WHERE trim(x) <> ''))""")

    R: dict = {"db": path, "at": datetime.now().isoformat(timespec="seconds"), "coverage": {}, "inferred": {}, "paths": {}}
    C = R["coverage"]

    def cov(name, table, cond, where="1=1"):
        n, k = one(f"SELECT count(*), count(*) FILTER (WHERE {cond}) FROM {table} WHERE {where}")
        C[name] = {"n": n, "linked": k, "pct": pct(k, n)}

    def linkcond(table, key_expr, dst="molecule"):
        return f"EXISTS (SELECT 1 FROM hl WHERE hl.src_table = '{table}' AND hl.src_key = {key_expr} AND hl.dst_type = '{dst}')"

    def inferred(name, table, dst="molecule"):
        n = one(f"SELECT count(DISTINCT src_key) FROM entity_links WHERE src_table = ? AND dst_type = ? AND confidence < {HIGH}", table, dst)[0]
        R["inferred"][name] = n

    # ---- #4 molecule resolution over text sources
    br_key = "coalesce(license_number, '') || '|' || coalesce(brand_norm, '') || '|' || coalesce(firm_name, '') || '|' || md5(coalesce(generic_name, ''))"
    cov("brand_registry -> molecule", "brand_registry", linkcond("brand_registry", br_key))
    cov("brand_first_seen -> molecule", "brand_first_seen", linkcond("brand_first_seen", "source || '|' || key"))
    cov("usfda recall -> molecule", "usfda_actions", linkcond("usfda_actions", "CAST(id AS VARCHAR)"), "kind = 'recall'")
    cov("trial -> molecule", "trials", f"(molecule_ids IS NOT NULL AND molecule_ids <> '') OR {linkcond('trials', 'nct_id')}")
    cov("news -> molecule", "news", f"(molecule_ids IS NOT NULL AND molecule_ids <> '') OR {linkcond('news', 'CAST(id AS VARCHAR)')}")
    pr_key = ("buyer || '|' || coalesce(tender_no, '') || '|' || coalesce(item_code, '') || '|' || coalesce(supplier, '') || '|' || "
              "coalesce(unit, '') || '|' || coalesce(level, '') || '|' || coalesce(CAST(rate AS VARCHAR), '')")
    cov("tender -> molecule", "procurement_rates", f"(molecule_ids IS NOT NULL AND molecule_ids <> '') OR {linkcond('procurement_rates', pr_key)}")
    for name, t in [("brand_registry", "brand_registry"), ("brand_first_seen", "brand_first_seen"), ("usfda", "usfda_actions"),
                    ("trials", "trials"), ("news", "news"), ("tenders", "procurement_rates")]:
        inferred(f"{name} -> molecule (inferred only)", t)

    # ---- #6 US / EU status reachable from a product (exact ingredient set)
    act = "NOT coalesce(is_discontinued, false) AND lower(name) NOT LIKE 'lorem%'"
    c.execute("""CREATE TEMP TABLE pset AS SELECT DISTINCT dst_id s, CAST(src_key AS INTEGER) combo_id FROM hl
                 WHERE src_table = 'combos' AND dst_type = 'ingredient_set'""")
    c.execute("""CREATE TEMP TABLE obset AS SELECT DISTINCT l.dst_id s, o.application_number, o.product_number FROM hl l
                 JOIN us_orange_book o ON o.application_number || '|' || o.product_number = l.src_key
                 WHERE l.src_table = 'us_orange_book' AND l.dst_type = 'ingredient_set'""")
    cov("product -> US Orange Book (same ingredient set)", "products p",
        "EXISTS (SELECT 1 FROM pset JOIN obset USING (s) WHERE pset.combo_id = p.combo_id)", act)
    cov("product -> live US patent/exclusivity (same set)", "products p",
        """EXISTS (SELECT 1 FROM pset JOIN obset USING (s) JOIN us_patents u ON u.application_number = obset.application_number
                   AND u.product_number = obset.product_number WHERE pset.combo_id = p.combo_id AND (u.expires_on IS NULL OR u.expires_on >= current_date))""", act)
    cov("product -> EMA (same set)", "products p",
        "EXISTS (SELECT 1 FROM pset JOIN hl e ON e.dst_id = pset.s AND e.src_table = 'ema_medicines' WHERE pset.combo_id = p.combo_id)", act)
    cov("molecule -> US Orange Book (single-ingredient set)", "molecules m", "EXISTS (SELECT 1 FROM obset WHERE obset.s = CAST(m.id AS VARCHAR))")

    # ---- #9 events with entities
    cov("event -> any entity", "events e", "e.entity_type IS NOT NULL OR EXISTS (SELECT 1 FROM event_entities x WHERE x.event_id = e.id AND x.confidence >= 0.85)")
    cov("event -> 2+ entities", "events e", f"(SELECT count(*) FROM event_entities x WHERE x.event_id = e.id AND x.confidence >= {HIGH}) >= 2")
    for et in ("molecule", "ingredient_set", "company", "parent"):
        cov(f"event -> {et}", "events e", f"(e.entity_type = '{et}') OR EXISTS (SELECT 1 FROM event_entities x WHERE x.event_id = e.id AND x.entity_type = '{et}' AND x.confidence >= {HIGH})")

    # ---- #11 price history
    n2, mixed = one("""WITH s AS (SELECT product_id, min(mrp) lo, max(mrp) hi FROM price_observations WHERE mrp > 0 GROUP BY 1 HAVING count(*) > 1)
                       SELECT count(*), count(*) FILTER (WHERE hi / lo >= 1.8) FROM s""")
    C["price history: products with 2+ points, raw jump >= 1.8x"] = {"n": n2, "linked": mixed, "pct": pct(mixed, n2)}
    n2u, okser, jump = one("""WITH s AS (SELECT product_id, count(*) n, min(unit_price) lo, max(unit_price) hi FROM price_unit_obs
                                         WHERE comparable AND unit_price > 0 GROUP BY 1)
                              SELECT (SELECT count(DISTINCT product_id) FROM price_unit_obs), count(*) FILTER (WHERE n >= 2),
                                     count(*) FILTER (WHERE n >= 2 AND hi / lo >= 1.8) FROM s""")
    C["price history: products with a comparable per-unit series (2+ points)"] = {"n": n2, "linked": okser, "pct": pct(okser, n2)}
    C["price history: comparable series still jumping >= 1.8x"] = {"n": okser, "linked": jump, "pct": pct(jump, okser)}

    # ---- #12 bans -> combos
    cov("banned FDC -> combo", "reg_banned_fdc b",
        f"EXISTS (SELECT 1 FROM combos k WHERE k.mkey = b.mkey) OR {linkcond('reg_banned_fdc', 'CAST(b.id AS VARCHAR)', 'combo')}")
    inferred("banned FDC -> combo (inferred only)", "reg_banned_fdc", "combo")

    # ---- #5 / #3
    cov("brand_first_seen -> company", "brand_first_seen", f"company_id IS NOT NULL OR {linkcond('brand_first_seen', 'source || chr(124) || key', 'company')}")
    cov("brand_first_seen (post-baseline) -> company", "brand_first_seen",
        f"company_id IS NOT NULL OR {linkcond('brand_first_seen', 'source || chr(124) || key', 'company')}", "NOT baseline")
    cov("molecule -> dated India launch signal (high)", "molecules m",
        f"EXISTS (SELECT 1 FROM launch_signals l WHERE l.confidence >= {HIGH} AND list_contains(string_split(l.ingredient_set, ','), CAST(m.id AS VARCHAR)))")
    cov("molecule -> any dated launch signal (incl. inferred)", "molecules m",
        "EXISTS (SELECT 1 FROM launch_signals l WHERE list_contains(string_split(l.ingredient_set, ','), CAST(m.id AS VARCHAR)))")
    cov("company -> group (curated)", "companies", "parent_id IS NOT NULL")
    cov("company -> group (curated or auto)", "companies c",
        f"parent_id IS NOT NULL OR {linkcond('companies', 'CAST(c.id AS VARCHAR)', 'auto_group')}")
    cov("company -> multi-company auto-group (name variants)", "companies c",
        f"EXISTS (SELECT 1 FROM hl WHERE hl.src_table = 'companies' AND hl.src_key = CAST(c.id AS VARCHAR) AND hl.method = 'name_variant')")
    cov("active product -> group (curated)", "products p",
        "EXISTS (SELECT 1 FROM companies c WHERE c.id = p.company_id AND c.parent_id IS NOT NULL)", act)
    cov("active product -> group (curated or auto)", "products p",
        f"""EXISTS (SELECT 1 FROM companies c WHERE c.id = p.company_id AND (c.parent_id IS NOT NULL OR
            EXISTS (SELECT 1 FROM hl WHERE hl.src_table = 'companies' AND hl.src_key = CAST(c.id AS VARCHAR) AND hl.dst_type = 'auto_group')))""", act)
    cov("approval -> company", "reg_approvals a", linkcond("reg_approvals", "CAST(a.id AS VARCHAR)", "company"), "applicant IS NOT NULL")
    cov("tender -> company", "procurement_rates", f"company_id IS NOT NULL OR {linkcond('procurement_rates', pr_key, 'company')}")

    # ---- the five paths
    P = R["paths"]
    # P1 NSQ batch -> product -> molecule -> maker -> group -> ticker -> price reaction -> news (NSQ since 2025)
    r = one("""SELECT count(*),
        count(*) FILTER (WHERE n.company_id IS NOT NULL AND n.molecule_ids IS NOT NULL AND EXISTS (
            SELECT 1 FROM products p WHERE p.company_id = n.company_id AND NOT EXISTS (
              SELECT 1 FROM unnest(string_split(n.molecule_ids, ',')) t(m) WHERE NOT EXISTS (
                SELECT 1 FROM product_molecules pm WHERE pm.product_id = p.id AND pm.molecule_id = CAST(t.m AS INTEGER))))),
        count(*) FILTER (WHERE n.molecule_ids IS NOT NULL),
        count(*) FILTER (WHERE n.company_id IS NOT NULL),
        count(*) FILTER (WHERE c.parent_id IS NOT NULL),
        count(*) FILTER (WHERE c.parent_id IS NOT NULL OR EXISTS (SELECT 1 FROM hl WHERE hl.src_table = 'companies'
                         AND hl.src_key = CAST(n.company_id AS VARCHAR) AND hl.dst_type = 'auto_group')),
        count(*) FILTER (WHERE pa.ticker IS NOT NULL),
        count(*) FILTER (WHERE pa.ticker IS NOT NULL AND EXISTS (SELECT 1 FROM quote_history h WHERE h.ticker = pa.ticker || '.NS'
             AND h.d BETWEEN strptime(n.alert_month || '-01', '%Y-%m-%d') AND strptime(n.alert_month || '-01', '%Y-%m-%d') + INTERVAL 45 DAY)),
        count(*) FILTER (WHERE pa.id IS NOT NULL AND EXISTS (SELECT 1 FROM news w WHERE list_contains(string_split(w.parent_ids, ','), CAST(pa.id AS VARCHAR))
             AND w.published_at BETWEEN strptime(n.alert_month || '-01', '%Y-%m-%d') - INTERVAL 30 DAY AND strptime(n.alert_month || '-01', '%Y-%m-%d') + INTERVAL 60 DAY)),
        count(*) FILTER (WHERE n.molecule_ids IS NOT NULL AND pa.ticker IS NOT NULL AND EXISTS (
            SELECT 1 FROM products p WHERE p.company_id = n.company_id AND NOT EXISTS (
              SELECT 1 FROM unnest(string_split(n.molecule_ids, ',')) t(m) WHERE NOT EXISTS (
                SELECT 1 FROM product_molecules pm WHERE pm.product_id = p.id AND pm.molecule_id = CAST(t.m AS INTEGER))))
            AND EXISTS (SELECT 1 FROM quote_history h WHERE h.ticker = pa.ticker || '.NS'
             AND h.d BETWEEN strptime(n.alert_month || '-01', '%Y-%m-%d') AND strptime(n.alert_month || '-01', '%Y-%m-%d') + INTERVAL 45 DAY)
            AND EXISTS (SELECT 1 FROM news w WHERE list_contains(string_split(w.parent_ids, ','), CAST(pa.id AS VARCHAR))
             AND w.published_at BETWEEN strptime(n.alert_month || '-01', '%Y-%m-%d') - INTERVAL 30 DAY AND strptime(n.alert_month || '-01', '%Y-%m-%d') + INTERVAL 60 DAY))
        FROM reg_nsq n LEFT JOIN companies c ON c.id = n.company_id LEFT JOIN parents pa ON pa.id = c.parent_id
        WHERE n.alert_month >= '2025-01'""")
    P["P1 NSQ"] = dict(zip(["start", "product (resolvable)", "molecule", "maker", "group", "group (incl. auto)", "ticker", "price window", "news", "all hops"], r))

    # P2 SEC -> molecule -> approval -> brand registration -> NPPA price -> first listing (SEC since 2024)
    c.execute(f"""CREATE TEMP TABLE sec2 AS SELECT id, meeting_date, sortset(molecule_ids) s FROM sec_items
                  WHERE meeting_date >= DATE '2024-01-01'""")
    c.execute(f"""CREATE TEMP TABLE brset AS SELECT DISTINCT s FROM molset WHERE src_table = 'brand_registry'""")
    # dated launch signals (#5): registry arrivals and NPPA launch prices are high-confidence; CDCI record dates are not
    c.execute(f"""CREATE TEMP TABLE launchset AS SELECT ingredient_set s, min(dated_on) first_seen FROM launch_signals
                  WHERE confidence >= {HIGH} AND ingredient_set IS NOT NULL GROUP BY 1""")
    r = one("""SELECT count(*), count(*) FILTER (WHERE s IS NOT NULL),
        count(*) FILTER (WHERE s IS NOT NULL AND EXISTS (SELECT 1 FROM reg_approvals a WHERE sortset(a.molecule_ids) = sec2.s AND a.approved_on >= sec2.meeting_date)),
        count(*) FILTER (WHERE s IS NOT NULL AND s IN (SELECT s FROM brset)),
        count(*) FILTER (WHERE s IS NOT NULL AND EXISTS (SELECT 1 FROM nppa_retail_prices r WHERE sortset(r.molecule_ids) = sec2.s)),
        count(*) FILTER (WHERE s IS NOT NULL AND s IN (SELECT s FROM launchset)),
        count(*) FILTER (WHERE s IS NOT NULL AND s IN (SELECT s FROM launchset) AND s IN (SELECT s FROM brset)
            AND EXISTS (SELECT 1 FROM reg_approvals a WHERE sortset(a.molecule_ids) = sec2.s AND a.approved_on >= sec2.meeting_date)
            AND EXISTS (SELECT 1 FROM nppa_retail_prices r WHERE sortset(r.molecule_ids) = sec2.s))
        FROM sec2""")
    P["P2 SEC"] = dict(zip(["start", "molecule", "later approval (same set)", "brand registration (same set)", "NPPA retail price (same set)",
                            "dated first listing (same set)", "all hops"], r))

    # P3 US FDA action -> plant -> company -> group -> ticker -> US applications (Indian actions)
    r = one(f"""SELECT count(*), 0,
        count(*) FILTER (WHERE a.parent_id IS NOT NULL OR {linkcond('usfda_actions', 'CAST(a.id AS VARCHAR)', 'parent')}),
        count(*) FILTER (WHERE pa.ticker IS NOT NULL),
        count(*) FILTER (WHERE EXISTS (SELECT 1 FROM us_applications u WHERE u.parent_id = a.parent_id)),
        count(*) FILTER (WHERE {linkcond('usfda_actions', 'CAST(a.id AS VARCHAR)')}),
        0
        FROM usfda_actions a LEFT JOIN parents pa ON pa.id = a.parent_id WHERE a.country ILIKE '%india%'""")
    P["P3 US FDA"] = dict(zip(["start (India)", "plant", "group", "ticker", "US applications", "molecule (recalls)", "all hops (needs plant)"], r))

    # P4 tender -> molecule -> product -> maker -> quality record
    c.execute(f"""CREATE TEMP TABLE tmol AS SELECT {pr_key} k, company_id,
                  coalesce(NULLIF(split_part(molecule_ids, ',', 1), ''),
                           (SELECT min(dst_id) FROM hl WHERE hl.src_table = 'procurement_rates' AND hl.src_key = {pr_key} AND hl.dst_type = 'molecule')) m
                  FROM procurement_rates""")
    r = one("""SELECT count(*), count(m), count(company_id),
        count(*) FILTER (WHERE company_id IS NOT NULL AND m IS NOT NULL AND EXISTS (SELECT 1 FROM products p JOIN product_molecules pm ON pm.product_id = p.id
            WHERE p.company_id = tmol.company_id AND pm.molecule_id = CAST(tmol.m AS INTEGER))),
        count(*) FILTER (WHERE company_id IS NOT NULL AND EXISTS (SELECT 1 FROM reg_nsq n WHERE n.company_id = tmol.company_id)),
        count(*) FILTER (WHERE company_id IS NOT NULL AND m IS NOT NULL AND EXISTS (SELECT 1 FROM products p JOIN product_molecules pm ON pm.product_id = p.id
            WHERE p.company_id = tmol.company_id AND pm.molecule_id = CAST(tmol.m AS INTEGER))
            AND EXISTS (SELECT 1 FROM reg_nsq n WHERE n.company_id = tmol.company_id))
        FROM tmol""")
    P["P4 Tender"] = dict(zip(["start", "molecule", "supplier company", "supplier's product", "supplier quality record", "all hops"], r))

    # P5 patent -> molecule -> US generics -> India products -> India launch
    r = one("""WITH pm AS (SELECT DISTINCT CAST(t.m AS INTEGER) mid FROM us_patents, unnest(string_split(molecule_ids, ',')) t(m)
                           WHERE molecule_ids IS NOT NULL AND expires_on >= current_date)
        SELECT count(*),
          count(*) FILTER (WHERE EXISTS (SELECT 1 FROM us_orange_book o WHERE o.app_type = 'A' AND list_contains(string_split(o.molecule_ids, ','), CAST(pm.mid AS VARCHAR)))),
          count(*) FILTER (WHERE EXISTS (SELECT 1 FROM product_molecules x WHERE x.molecule_id = pm.mid)),
          count(*) FILTER (WHERE EXISTS (SELECT 1 FROM launchset WHERE list_contains(string_split(launchset.s, ','), CAST(pm.mid AS VARCHAR)))),
          count(*) FILTER (WHERE EXISTS (SELECT 1 FROM us_orange_book o WHERE o.app_type = 'A' AND list_contains(string_split(o.molecule_ids, ','), CAST(pm.mid AS VARCHAR)))
            AND EXISTS (SELECT 1 FROM launchset WHERE list_contains(string_split(launchset.s, ','), CAST(pm.mid AS VARCHAR))))
        FROM pm""")
    P["P5 Patent"] = dict(zip(["start (molecules with live US patents)", "US ANDA generics", "India products", "dated India launch", "all hops"], r))

    for k, v in P.items():
        vals = list(v.values())
        v["end_to_end_pct"] = pct(vals[-1], vals[0])
    R["link_totals"] = [dict(zip(["linker", "links", "high"], x)) for x in c.execute(
        f"SELECT linker, count(*), count(*) FILTER (WHERE confidence >= {HIGH}) FROM entity_links GROUP BY 1 ORDER BY 1").fetchall()]
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(R, f, indent=1, default=str)
    return R


if __name__ == "__main__":
    args = sys.argv[1:]
    out = args[args.index("--json") + 1] if "--json" in args else None
    res = main(args[0], out)
    for k, v in res["coverage"].items():
        print(f"{v['pct'] if v['pct'] is not None else '-':>6}%  {v['linked']:>8,} / {v['n']:<8,}  {k}")
    for k, v in res["inferred"].items():
        print(f"   inferred-only records: {v:>7,}  {k}")
    for k, v in res["paths"].items():
        print(k, json.dumps(v))
