"""Plant stage 1: the maker (manufacturing firm) entity, across every source that names one, with the role it plays.

A maker is a legal firm, keyed by its strict firm key (companies.strict_key: legal words dropped, spelling synonyms
folded, initials and an in-name "India" kept; addresses and plant names after the firm name are cut). Two plants of
one firm are one maker here; plants / sites are stage 2.

Sources and roles (entity_links, dst_type 'maker'):
  reg_nsq.manufacturer           manufacturer of the failed batch (label)
  brand_registry.firm_name       licensed manufacturer that registered the brand (Rule 84AB)
  usfda_actions.firm             firm named in a US FDA recall or import alert
  reg_approvals.applicant        CDSCO permission holder (may be an importer)
  cdci_supplier.supplier_name    supplier in CDCI
  procurement_rates.supplier     state tender supplier
  firm_debarments.firm           debarred firm
Confidence 0.9 when the firm key is distinctive, 0.7 (inferred) when it is only generic words and initials
("S P Pharma"), which several firms can share.

Maker -> catalog company (marketer) by equal firm key (0.9), and through it the curated group or auto-group; maker ->
curated group also by the curated group name patterns (matcher.parent_for, 0.85).

Contract-manufacturing map: a brand registration (maker) -> catalog SKUs whose name starts with the brand's first
word and whose canonical ingredient set equals the registration's complete set: 0.85 when the first two words match,
0.7 when only the first does. maker_makes_for aggregates these into maker -> marketer pairs (own or contract).
Source tables are not modified.
"""
import re
from collections import Counter, defaultdict

import pandas as pd

from .. import db, matcher
from .companies import distinctive, strict_key
from .store import HIGH, ensure, licence_of

SOURCES = [   # (table, key expression, name column, role, where)
    ("reg_nsq", "CAST(id AS VARCHAR)", "manufacturer", "batch_manufacturer", "manufacturer IS NOT NULL"),
    ("brand_registry", "coalesce(license_number, '') || '|' || coalesce(brand_norm, '') || '|' || coalesce(firm_name, '') || '|' || md5(coalesce(generic_name, ''))",
     "firm_name", "brand_licensee", "firm_name IS NOT NULL"),
    ("usfda_actions", "CAST(id AS VARCHAR)", "firm", "us_fda_firm", "firm IS NOT NULL"),
    ("reg_approvals", "CAST(id AS VARCHAR)", "applicant", "approval_applicant", "applicant IS NOT NULL"),
    ("cdci_supplier", "CAST(identifier AS VARCHAR)", "supplier_name", "cdci_supplier", "supplier_name IS NOT NULL"),
    ("procurement_rates", "buyer || '|' || coalesce(tender_no, '') || '|' || coalesce(item_code, '') || '|' || coalesce(supplier, '') || '|' || "
     "coalesce(unit, '') || '|' || coalesce(level, '') || '|' || coalesce(CAST(rate AS VARCHAR), '')", "supplier", "tender_supplier", "supplier IS NOT NULL"),
    ("firm_debarments", "dedupe_key", "firm", "debarred_firm", "firm IS NOT NULL"),
]

DDL = """
CREATE TABLE IF NOT EXISTS makers (
    maker_key   VARCHAR PRIMARY KEY,   -- 'mk:<strict firm key>'
    name        VARCHAR,               -- the most frequent spelling
    distinctive BOOLEAN,               -- false: only generic words / initials, may be several firms
    records     INTEGER,
    roles       VARCHAR,               -- JSON {role: records}
    company_id  INTEGER,               -- catalog company (marketer) with the same firm key
    parent_id   INTEGER,               -- curated group (via the company, or the curated name patterns)
    auto_group  VARCHAR,               -- auto-group of that company when it is outside a curated group
    country     VARCHAR
);
CREATE TABLE IF NOT EXISTS maker_makes_for (   -- contract-manufacturing map from brand registrations
    maker_key   VARCHAR,
    company_id  INTEGER,               -- marketer of the matched SKUs
    relation    VARCHAR,               -- own (same firm) | same_group (curated group) | contract
    skus        INTEGER,
    brands      INTEGER,
    example     VARCHAR,
    confidence  DOUBLE
);
"""


UNIT_OF = re.compile(r"\(?\s*\ba\s+(?:unit|div(?:ision)?)\.?\s+of\b.*$", re.I)


ROLE_PREFIX = re.compile(r"^\s*(?:m\s*/\s*s\.?\s*)?(?:supplied|manufactured|mfd|mfg|marketed|distributed|packed)\.?\s*(?:by|for)\s*[:.-]?\s*", re.I)


def clean(name: str) -> str:
    """Firm name without a leading role ("Supplied by ...") or "(a unit / division of <owner>)"; the owner is resolved
    separately (matcher.company_for)."""
    return UNIT_OF.sub("", ROLE_PREFIX.sub("", name or "")).strip(" -(,")


def _sql_links(w, linker: str, rows_sql: str) -> int:
    w.execute("DELETE FROM entity_links WHERE linker = ?", [linker]).fetchall()
    # rows_sql yields, in order: src_table, src_key, dst_type, dst_id, method, confidence, evidence, licence
    # every result is read to the end: the server's DuckDB refuses new work while a result is pending
    w.execute(f"""INSERT INTO entity_links SELECT '{linker}', q.*, now() FROM ({rows_sql}) q ON CONFLICT DO NOTHING""").fetchall()
    return w.execute("SELECT count(*) FROM entity_links WHERE linker = ?", [linker]).fetchall()[0][0]


def run() -> list[dict]:
    ensure()
    with db.writer() as w:
        w.execute(DDL)
    cur = db.cursor()
    matcher._load()
    # every firm string -> maker key (distinct strings only: a few thousand per source)
    names: dict[str, str] = {}
    spell: dict[str, Counter] = defaultdict(Counter)
    roles: dict[str, Counter] = defaultdict(Counter)
    country: dict[str, str] = {}
    for table, keyx, col, role, where in SOURCES:
        for nm, n, *rest in cur.execute(f"SELECT {col}, count(*){', any_value(country)' if table == 'usfda_actions' else ''} FROM {table} WHERE {where} GROUP BY 1").fetchall():
            k = strict_key(clean(nm))
            if len(k) < 3:
                continue
            names[nm] = "mk:" + k
            spell["mk:" + k][matcher._firm_text(clean(nm)).title()] += n
            roles["mk:" + k][role] += n
            if rest and rest[0]:
                country.setdefault("mk:" + k, rest[0])
    comp_by_key: dict[str, tuple] = {}
    for cid, nm, ac, pid in cur.execute("SELECT id, name, coalesce(active_count, 0), parent_id FROM companies ORDER BY active_count DESC").fetchall():
        comp_by_key.setdefault("mk:" + strict_key(nm), (cid, pid))
    auto = dict(cur.execute("""SELECT src_key, dst_id FROM entity_links WHERE linker = 'company:auto_groups' AND dst_type = 'auto_group'""").fetchall())
    makers = []
    import json
    raw_names: dict[str, list[str]] = defaultdict(list)
    for nm, k in names.items():
        raw_names[k].append(nm)
    comp_parent = dict(cur.execute("SELECT id, parent_id FROM companies").fetchall())
    via: dict[str, str] = {}
    for mk, sp in spell.items():
        nm = sp.most_common(1)[0][0]
        cid, pid = comp_by_key.get(mk, (None, None))
        via[mk] = "equal_firm_key" if cid else ""
        if not cid:   # "Alkem Health Science (a unit of Alkem Laboratories Ltd)" -> the owning catalog company
            for raw in raw_names[mk][:5]:
                c2 = matcher.company_for(raw)
                if c2:
                    cid, pid, via[mk] = c2, comp_parent.get(c2), "company_matcher"
                    break
        pat = pid or matcher.parent_for(nm)
        makers.append({"maker_key": mk, "name": nm, "distinctive": distinctive(mk[3:]), "records": sum(roles[mk].values()),
                       "roles": json.dumps(dict(roles[mk])), "company_id": cid, "parent_id": pat, "via": via[mk],
                       "auto_group": auto.get(str(cid)) if cid and not pid else None, "country": country.get(mk)})
    mdf = pd.DataFrame(makers)
    namedf = pd.DataFrame([{"name": n, "maker_key": k} for n, k in names.items()])
    lic_m = licence_of("companies")
    out = []
    with db.writer() as w:
        w.execute("DELETE FROM makers")
        w.register("_m", mdf)
        w.execute("""INSERT INTO makers SELECT maker_key, name, distinctive, records::INTEGER, roles, company_id::INTEGER, parent_id::INTEGER,
                     auto_group, country FROM _m""")
        w.execute("CREATE OR REPLACE TEMP TABLE _via AS SELECT maker_key, via FROM _m")
        w.unregister("_m")
        w.register("_n", namedf)
        for table, keyx, col, role, where in SOURCES:
            lic = licence_of(table)
            n = _sql_links(w, f"maker:{table}", f"""
                SELECT '{table}', {keyx}, 'maker', n.maker_key,
                       'firm_key:{role}' || CASE WHEN m.distinctive THEN '' ELSE ':generic_name' END AS meth,
                       CASE WHEN m.distinctive THEN 0.9 ELSE 0.7 END AS conf,
                       '{role}: "' || replace(left(t.{col}, 120), chr(10), ' ') || '" -> firm key ' || substr(n.maker_key, 4) AS ev, '{lic}' AS lic
                FROM {table} t JOIN _n n ON n.name = t.{col} JOIN makers m ON m.maker_key = n.maker_key WHERE {where.replace(col, 't.' + col)}""")
            out.append({"linker": f"maker:{table}", "links": n})
        w.unregister("_n")
        # maker -> company / group
        n = _sql_links(w, "maker:company", f"""
            SELECT 'makers', maker_key, 'company', CAST(company_id AS VARCHAR), v.via,
                   CASE WHEN distinctive THEN 0.9 ELSE 0.7 END - CASE WHEN v.via = 'company_matcher' THEN 0.05 ELSE 0 END,
                   'maker ' || name || ' = catalog company ' || company_id || ' (' || v.via || ')',
                   '{lic_m}' FROM makers JOIN _via v USING (maker_key) WHERE company_id IS NOT NULL
            UNION ALL
            SELECT 'makers', maker_key, 'parent', CAST(parent_id AS VARCHAR), CASE WHEN company_id IS NOT NULL AND parent_id IS NOT NULL
                   AND EXISTS (SELECT 1 FROM companies c WHERE c.id = makers.company_id AND c.parent_id = makers.parent_id) THEN 'via_company'
                   ELSE 'curated_name_pattern' END, CASE WHEN distinctive THEN 0.9 ELSE 0.7 END - CASE WHEN company_id IS NULL THEN 0.05 ELSE 0 END,
                   'maker ' || name || ' -> curated group ' || parent_id, 'open' FROM makers WHERE parent_id IS NOT NULL
            UNION ALL
            SELECT 'makers', maker_key, 'auto_group', auto_group, 'via_company', CASE WHEN distinctive THEN 0.9 ELSE 0.7 END,
                   'maker ' || name || ' -> auto-group ' || auto_group, '{lic_m}' FROM makers WHERE auto_group IS NOT NULL""")
        out.append({"linker": "maker:company", "links": n})
        # contract-manufacturing map: brand registration -> SKU (brand word + exact canonical ingredient set)
        lic_b = licence_of("brand_registry", "products")
        n = _sql_links(w, "maker:brand_product", f"""
            WITH br AS (SELECT l.src_key, string_agg(l.dst_id, ',' ORDER BY CAST(l.dst_id AS INTEGER)) s FROM entity_links l
                        WHERE l.linker = 'mol:brand_registry' AND l.dst_type = 'molecule' AND l.confidence >= {HIGH}
                        GROUP BY 1 HAVING count(*) FILTER (WHERE l.method LIKE '%partial%') = 0),
                 b AS (SELECT b.*, br.s, coalesce(b.license_number, '') || '|' || coalesce(b.brand_norm, '') || '|' || coalesce(b.firm_name, '') || '|' ||
                              md5(coalesce(b.generic_name, '')) k,
                              split_part(b.brand_norm, ' ', 1) w1, split_part(b.brand_norm, ' ', 2) w2
                       FROM brand_registry b JOIN br ON br.src_key = coalesce(b.license_number, '') || '|' || coalesce(b.brand_norm, '') || '|' ||
                            coalesce(b.firm_name, '') || '|' || md5(coalesce(b.generic_name, ''))
                       WHERE length(split_part(b.brand_norm, ' ', 1)) >= 4
                         -- a "brand" that is the generic name ("Amlodipine 5") matches every marketer's generic SKU
                         AND split_part(b.brand_norm, ' ', 1) NOT IN (SELECT split_part(mkey, ' ', 1) FROM molecules)
                         AND split_part(b.brand_norm, ' ', 1) NOT IN (SELECT split_part(lower(name), ' ', 1) FROM molecules)),
                 ps AS (SELECT CAST(src_key AS INTEGER) combo_id, dst_id s FROM entity_links WHERE linker = 'global:combo_sets'),
                 p AS (SELECT p.id, p.name, p.company_id, ps.s, split_part(p.name_norm, ' ', 1) w1, split_part(p.name_norm, ' ', 2) w2
                       FROM products p JOIN ps ON ps.combo_id = p.combo_id WHERE NOT coalesce(p.is_discontinued, false))
            SELECT 'brand_registry', b.k, 'product', CAST(p.id AS VARCHAR),
                   CASE WHEN b.w2 <> '' AND b.w2 = p.w2 THEN 'brand_two_words_and_set' ELSE 'brand_first_word_and_set' END,
                   CASE WHEN b.w2 <> '' AND b.w2 = p.w2 THEN 0.85 ELSE 0.7 END,
                   'registered brand "' || b.brand_name || '" (' || b.firm_name || ') = SKU "' || p.name || '", same ingredients', '{lic_b}'
            FROM b JOIN p ON p.w1 = b.w1 AND p.s = b.s""")
        # a registration matching SKUs of several marketers (co-marketing or a shared brand word) is not evidence of who
        # makes for whom: those links stay inferred
        w.execute(f"""UPDATE entity_links SET confidence = 0.7, method = method || ':several_marketers'
                      WHERE linker = 'maker:brand_product' AND confidence >= {HIGH} AND src_key IN (
                        SELECT l.src_key FROM entity_links l JOIN products p ON CAST(p.id AS VARCHAR) = l.dst_id
                        WHERE l.linker = 'maker:brand_product' AND l.confidence >= {HIGH} GROUP BY 1 HAVING count(DISTINCT p.company_id) > 1)""")
        out.append({"linker": "maker:brand_product", "links": n})
        w.execute("DELETE FROM maker_makes_for")
        w.execute(f"""INSERT INTO maker_makes_for
            SELECT m.dst_id, p.company_id,
                   CASE WHEN any_value(mk.company_id) = p.company_id THEN 'own'
                        WHEN any_value(mk.parent_id) IS NOT NULL AND any_value(mk.parent_id) = any_value(co.parent_id) THEN 'same_group'
                        ELSE 'contract' END,
                   count(DISTINCT p.id), count(DISTINCT bp.src_key), any_value(p.name), max(least(bp.confidence, m.confidence))
            FROM entity_links bp JOIN entity_links m ON m.linker = 'maker:brand_registry' AND m.src_key = bp.src_key
            JOIN products p ON CAST(p.id AS VARCHAR) = bp.dst_id
            JOIN makers mk ON mk.maker_key = m.dst_id LEFT JOIN companies co ON co.id = p.company_id
            WHERE bp.linker = 'maker:brand_product' AND bp.confidence >= {HIGH} AND p.company_id IS NOT NULL
            GROUP BY m.dst_id, p.company_id""")
        mf = w.execute("SELECT count(*), count(*) FILTER (WHERE relation = 'contract') FROM maker_makes_for").fetchall()[0]
        w.execute("DROP TABLE IF EXISTS _via")
        w.execute("INSERT INTO linker_runs VALUES ('makers', now(), now(), ?, ?, ?)",
                  [len(mdf), int(mdf.distinctive.sum()), f"{mf[0]:,} maker->marketer pairs ({mf[1]:,} contract)"])
    out.append({"linker": "makers", "links": len(mdf), "high": int(mdf.distinctive.sum()), "makes_for": mf[0], "contract": mf[1]})
    return out
