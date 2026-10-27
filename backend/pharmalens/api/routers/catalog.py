"""Search, products (brands/SKUs), salt combinations, molecules, companies, parent groups."""
import json
import time

from fastapi import APIRouter, HTTPException, Query

from ... import db
from ...normalize import norm
from ..common import SORTS, cleanrows, csv_response, ids, paged

router = APIRouter(tags=["catalog"])


def maybe(cur, sql: str, params=None) -> list[dict]:
    """Rows from a table a connector creates on first run; empty until it has."""
    import duckdb
    try:
        return db.rows(cur, sql, params)
    except duckdb.CatalogException:
        return []


def has_mol(col: str = "molecule_ids") -> str:
    return f"list_contains(string_split({col}, ','), ?)"


def enrichment(cur, mid: int) -> dict | None:
    e = maybe(cur, "SELECT * FROM molecule_enrichment WHERE molecule_id = ?", [mid])
    if not e:
        return None
    e = e[0]
    for k in ("atc", "mechanisms", "indications", "faers_top", "us_label", "us_label_meta", "faers_co", "faers_names", "chembl_ambiguous"):
        if isinstance(e.get(k), str):
            e[k] = json.loads(e[k])
    return e



def molecule_reference(cur, mids: list[int], form: str | None = None) -> dict | None:
    """Reference text for a product without its own label: the CDCI generic monograph for exactly this set of
    molecules (a combination gets the combination's monograph), else nothing; plus the US label for single molecules."""
    if not mids:
        return None
    subs = maybe(cur, f"""SELECT molecule_id, identifier FROM cdci_substance
                          WHERE molecule_id IN ({','.join('?' * len(mids))})""", mids)
    by_mol: dict[int, set] = {}
    for r in subs:
        by_mol.setdefault(int(r["molecule_id"]), set()).add(str(r["identifier"]))
    out: dict = {"scope": "molecule", "cdci": [], "us_label": None}
    if len(by_mol) == len(set(mids)):
        # every molecule is in CDCI: find generics whose substance set is exactly ours (any one substance per molecule)
        rows = maybe(cur, """SELECT generic_name, substance_identifier, therapeutic_role, classification_of_drugs, indication,
                                    contra_indication, interaction_with_drugs, dose_form
                             FROM cdci_generic WHERE indication IS NOT NULL OR contra_indication IS NOT NULL
                                                  OR interaction_with_drugs IS NOT NULL""")
        want = [v for v in by_mol.values()]
        hits = [r for r in rows if len(ids := set(str(r["substance_identifier"] or "").split("+"))) == len(want)
                and all(ids & w for w in want)]
        # prefer a monograph for the same dosage form (an injection should not show an oral tablet's entry)
        fam = FORM_FAMILY.get((form or "").strip().lower()) or tuple(w for w in (form or "").lower().split() if len(w) > 3)
        hits.sort(key=lambda r: (not any(w in (r["generic_name"] or "").lower() for w in fam), r["indication"] is None,
                                 len(r["generic_name"] or "")))
        out["cdci"] = hits[:3]
    if len(set(mids)) == 1:
        e = enrichment(cur, mids[0])
        if e and e.get("us_label"):
            out["us_label"] = {"sections": e["us_label"], "meta": e.get("us_label_meta")}
    return out if (out["cdci"] or out["us_label"]) else None

def procurement(cur, where: str, params: list, limit: int = 60) -> list[dict]:
    return maybe(cur, f"""SELECT buyer, state, item_code, item, kind, unit, rate, gst, level, supplier, company_id, tender_no,
                                 valid_from, valid_to, category, order_share, source_url FROM procurement_rates
                          WHERE {where} ORDER BY buyer, item, (level = 'L1') DESC, rate LIMIT {limit}""", params)

PRODUCT_COLS = """
    p.id, p.name, p.mrp, p.mrp_asof, p.unit_price, p.pack_size, p.dosage_form, p.composition,
    p.combo_id, p.therapeutic_class, p.rx_required, p.is_discontinued, p.in_stock, p.source_count,
    c.id AS company_id, c.name AS company, c.slug AS company_slug,
    pa.id AS parent_id, pa.name AS parent, pa.slug AS parent_slug, p.ban_level, p.ban_id
"""
PRODUCT_FROM = """
    FROM products p
    LEFT JOIN companies c ON c.id = p.company_id
    LEFT JOIN parents pa ON pa.id = c.parent_id
    LEFT JOIN combos k ON k.id = p.combo_id
"""


# ------------------------------------------------------------------ search
@router.get("/search")
def search(q: str = Query(..., min_length=2), limit: int = Query(8, le=30)):
    t0 = time.perf_counter()
    cur = db.cursor()
    n = norm(q)
    like, pre = f"%{n}%", f"{n}%"
    out = {}
    out["products"] = db.rows(cur, f"""
        SELECT p.id, p.name, p.mrp, p.dosage_form, c.name company, p.composition
        FROM products p LEFT JOIN companies c ON c.id = p.company_id
        WHERE p.name_norm LIKE ? ORDER BY (p.name_norm LIKE ?) DESC, p.source_count DESC, length(p.name) LIMIT ?""",
        [like, pre, limit])
    out["molecules"] = db.rows(cur, """
        SELECT id, name, product_count, therapeutic_class FROM molecules
        WHERE mkey LIKE ? ORDER BY (mkey LIKE ?) DESC, product_count DESC NULLS LAST LIMIT ?""", [like, pre, limit])
    out["combos"] = db.rows(cur, """
        SELECT id, label, product_count, company_count, is_banned FROM combos
        WHERE lower(label) LIKE ? AND molecule_count > 1 ORDER BY product_count DESC NULLS LAST LIMIT ?""",
        [f"%{q.lower()}%", min(limit, 6)])
    out["parents"] = db.rows(cur, """
        SELECT id, slug, name, ticker FROM parents WHERE lower(name) LIKE ? OR lower(ticker) LIKE ? LIMIT 5""",
        [f"%{q.lower()}%", f"{q.lower()}%"])
    out["companies"] = db.rows(cur, """
        SELECT id, slug, name, product_count FROM companies WHERE name_norm LIKE ?
        ORDER BY (name_norm LIKE ?) DESC, product_count DESC NULLS LAST LIMIT ?""", [like, pre, min(limit, 6)])
    return {"q": q, "took_ms": round((time.perf_counter() - t0) * 1000, 1),
            **{k: cleanrows(v) for k, v in out.items()}}


# ------------------------------------------------------------------ products
@router.get("/products")
def products(
    q: str | None = None, molecule_id: int | None = None, combo_id: int | None = None,
    company_id: int | None = None, parent_id: int | None = None, therapeutic_class: str | None = None,
    dosage_form: str | None = None, rx: bool | None = None, in_stock: bool | None = None,
    banned: bool | None = None, active_only: bool = False, min_mrp: float | None = None, max_mrp: float | None = None,
    mono: bool | None = None, sort: str = "reach", page: int = 1, limit: int = Query(50, le=500), format: str = "json",
):
    t0 = time.perf_counter()
    where, args = ["1=1"], []
    if q:
        where.append("p.name_norm LIKE ?"); args.append(f"%{norm(q)}%")
    if molecule_id:
        where.append("p.id IN (SELECT product_id FROM product_molecules WHERE molecule_id = ?)"); args.append(molecule_id)
    if combo_id:
        where.append("p.combo_id = ?"); args.append(combo_id)
    if company_id:
        where.append("p.company_id = ?"); args.append(company_id)
    if parent_id:
        where.append("c.parent_id = ?"); args.append(parent_id)
    if therapeutic_class:
        where.append("p.therapeutic_class = ?"); args.append(therapeutic_class)
    if dosage_form:
        where.append("p.dosage_form = ?"); args.append(dosage_form)
    if rx is not None:
        where.append("coalesce(p.rx_required, false) = ?"); args.append(rx)
    if in_stock is not None:
        where.append("p.in_stock = ?"); args.append(in_stock)
    if banned is not None:
        where.append("p.ban_level IS NOT NULL" if banned else "p.ban_level IS NULL")
    if active_only:
        where.append("coalesce(p.is_discontinued, false) = false")
    if min_mrp is not None:
        where.append("p.mrp >= ?"); args.append(min_mrp)
    if max_mrp is not None:
        where.append("p.mrp <= ?"); args.append(max_mrp)
    if mono is not None:
        where.append("p.molecule_count = 1" if mono else "p.molecule_count > 1")
    w = " AND ".join(where)
    cur = db.cursor()
    order = SORTS.get(sort, SORTS["reach"])
    if format == "csv":
        data = db.rows(cur, f"SELECT {PRODUCT_COLS} {PRODUCT_FROM} WHERE {w} ORDER BY {order} LIMIT 50000", args)
        return csv_response(data, "products")
    total = cur.execute(f"SELECT count(*) {PRODUCT_FROM} WHERE {w}", args).fetchone()[0]
    data = db.rows(cur, f"SELECT {PRODUCT_COLS} {PRODUCT_FROM} WHERE {w} ORDER BY {order} LIMIT ? OFFSET ?",
                   args + [limit, (page - 1) * limit])
    return paged(total, page, limit, data, took_ms=round((time.perf_counter() - t0) * 1000, 1))


@router.get("/products/{pid}")
def product(pid: int):
    cur = db.cursor()
    p = db.one(cur, f"""SELECT {PRODUCT_COLS}, p.mrp_legacy, p.action_class, p.chemical_class, p.habit_forming,
                           p.uses, p.side_effects, p.image_url, p.sources, p.indication_group, p.molecule_count, p.manufacturer_raw,
                           k.label AS combo_label, k.product_count AS combo_products, k.company_count AS combo_companies,
                           k.min_mrp AS combo_min, k.median_mrp AS combo_median, k.max_mrp AS combo_max
                        {PRODUCT_FROM} WHERE p.id = ?""", [pid])
    if not p:
        raise HTTPException(404, "product not found")
    p["molecules"] = db.rows(cur, """
        SELECT m.id, m.name, pm.strength, m.action_class, m.nppa_ceiling, m.is_nlem, m.product_count
        FROM product_molecules pm JOIN molecules m ON m.id = pm.molecule_id WHERE pm.product_id = ?""", [pid])
    mids = [m["id"] for m in p["molecules"]]
    p["interactions"] = None
    def parse_ix(raw):
        try:
            d = json.loads(raw)
            return [{"drug": a.strip(), "brands": b.strip(), "severity": e}
                    for a, b, e in zip(d.get("drug", []), d.get("brand", []), d.get("effect", []))]
        except (ValueError, TypeError):
            return []
    raw = cur.execute("SELECT raw FROM interactions WHERE product_id = ?", [pid]).fetchone()
    p["interactions"] = parse_ix(raw[0]) if raw else []
    p["interactions_source"] = "product" if p["interactions"] else None
    if not p["interactions"] and p["combo_id"]:
        # interaction lists describe the molecules, so another brand of the same molecules carries the same list
        for (other,) in cur.execute("""
                SELECT i.raw FROM interactions i JOIN products q ON q.id = i.product_id JOIN combos k ON k.id = q.combo_id
                WHERE k.mkey = (SELECT mkey FROM combos WHERE id = ?) AND len(json_extract(i.raw, '$.drug')::JSON[]) > 0
                ORDER BY len(json_extract(i.raw, '$.drug')::JSON[]) DESC LIMIT 1""", [p["combo_id"]]).fetchall():
            p["interactions"] = parse_ix(other)
            p["interactions_source"] = "same_molecules"
    p["interactions"] = p["interactions"] or None
    # same-composition ladder (cheapest first)
    p["equivalents"] = db.rows(cur, f"""
        SELECT {PRODUCT_COLS} {PRODUCT_FROM}
        WHERE p.combo_id = ? AND p.id <> ? AND p.mrp IS NOT NULL
          AND p.dosage_form IS NOT DISTINCT FROM ?
          AND coalesce(p.unit_price, 1e9) >= 0.15 * coalesce((SELECT median(unit_price) FROM products
                WHERE combo_id = ? AND dosage_form IS NOT DISTINCT FROM ?), 0)
        ORDER BY coalesce(p.unit_price, p.mrp) ASC LIMIT 25""",
        [p["combo_id"], pid, p["dosage_form"], p["combo_id"], p["dosage_form"]]) if p["combo_id"] else []
    info = db.one(cur, "SELECT * FROM product_info WHERE product_id = ?", [pid])
    if info:
        info["shared_from"] = None
    elif p["combo_id"]:
        # label advice describes the composition, so another brand of the same molecules carries it: prefer the
        # same strengths, then the same dosage form, then the fullest text; its brand name becomes this product's
        # strengths per molecule, e.g. "390:100mg|418:600mg"; unknown when any strength is missing
        sig = "|".join(f"{m['id']}:{(m['strength'] or '').lower().replace(' ', '')}"
                       for m in sorted(p["molecules"], key=lambda m: m["id"]))
        sig = sig if p["molecules"] and all(m["strength"] for m in p["molecules"]) else None
        info = db.one(cur, """
            WITH cand AS (
              SELECT i.*, q.id AS donor_id, q.name AS donor_name, q.dosage_form AS donor_form,
                     (SELECT string_agg(molecule_id || ':' || lower(replace(coalesce(strength, ''), ' ', '')), '|' ORDER BY molecule_id)
                      FROM product_molecules WHERE product_id = q.id) AS donor_sig
              FROM product_info i JOIN products q ON q.id = i.product_id JOIN combos k ON k.id = q.combo_id
              WHERE k.mkey = (SELECT mkey FROM combos WHERE id = ?) AND q.id <> ?)
            SELECT * FROM cand
            ORDER BY (donor_sig = ?) DESC NULLS LAST, (donor_form IS NOT DISTINCT FROM ?) DESC,
                     (safety IS NOT NULL) DESC, length(coalesce(introduction, '')) DESC, donor_id
            LIMIT 1""", [p["combo_id"], pid, sig, p["dosage_form"]])
        if info:
            donor = info.pop("donor_name")
            info.pop("donor_form")
            info["shared_from"] = {"id": info.pop("donor_id"), "name": donor,
                                   "same_strength": (info.pop("donor_sig") == sig) if sig else None}
            for k, v in info.items():
                if isinstance(v, str) and donor:
                    info[k] = v.replace(donor, p["name"])
    if info:
        for k in ("benefits", "quick_tips", "side_effects", "safety"):
            if isinstance(info.get(k), str):
                info[k] = json.loads(info[k])
    p["label"] = info
    p["price_history"] = db.rows(cur, "SELECT observed_on, mrp, source FROM price_observations WHERE product_id = ? ORDER BY observed_on", [pid])
    # the manufacturer's own price list entry (Form V): MRP with trade prices, newest first
    p["mfr_price"] = (maybe(cur, """
        SELECT effective_on, company_label, product AS list_name, pack, mrp, mrp_old, ptr, pts, gst, match_kind, pack_mrp,
               doc_url, doc_host
        FROM mfr_prices WHERE product_id = ? ORDER BY effective_on DESC NULLS LAST, match_kind = 'same_pack' DESC LIMIT 1""",
        [pid]) or [None])[0]
    # official launch prices NPPA fixed for the same molecules; this product's own marketer or group first
    p["nppa_notified"] = maybe(cur, """
        SELECT n.notified_on, n.so_number, n.kind, n.formulation, n.strength, n.unit, n.price, n.marketer, n.doc_url,
               c.slug AS company_slug, (n.company_id = ?) AS same_company, (c.parent_id = ?) AS same_group
        FROM nppa_retail_prices n LEFT JOIN companies c ON c.id = n.company_id
        WHERE n.molecule_ids = ?
        ORDER BY (n.company_id = ?) DESC NULLS LAST, (c.parent_id = ?) DESC NULLS LAST, n.notified_on DESC LIMIT 12""",
        [p["company_id"], p["parent_id"], ",".join(map(str, sorted(mids))), p["company_id"], p["parent_id"]]) if mids else []
    p["nppa_ceiling"] = db.rows(cur, f"""
        SELECT molecule_name, form_strength, ceiling_price, unit, notification, year FROM nppa_ceiling
        WHERE molecule_id IN ({','.join('?' * len(mids))}) ORDER BY year DESC""", mids) if mids else []
    p["jan_aushadhi"] = jan_aushadhi_for(cur, mids, p["molecule_count"] or len(mids),
                                         [m["strength"] for m in p["molecules"]], p["dosage_form"])
    # quality record of the same maker for the same molecules
    p["nsq_same_maker"] = db.rows(cur, """
        SELECT alert_month, category, product_text, batch_no, reason, lab, source_url FROM reg_nsq
        WHERE company_id = ? ORDER BY alert_month DESC NULLS LAST LIMIT 20""", [p["company_id"]]) if p["company_id"] else []
    p["nsq_same_molecule"] = cur.execute(
        f"""SELECT count(*) FROM reg_nsq WHERE {' OR '.join(["list_contains(string_split(molecule_ids, ','), ?)"] * len(mids))}""",
        [str(m) for m in mids]).fetchone()[0] if mids else 0
    p["ban"] = db.rows(cur, "SELECT id, combo_text, notification, notified_on, status, source_url FROM reg_banned_fdc WHERE id = ?", [p["ban_id"]]) if p["ban_id"] else []
    p["related_bans"] = db.rows(cur, """SELECT id, combo_text, notification, notified_on, status FROM reg_banned_fdc
                                        WHERE mkey = (SELECT mkey FROM combos WHERE id = ?) AND id IS DISTINCT FROM ?""", [p["combo_id"], p["ban_id"]]) if p["combo_id"] else []
    # licensing: CDSCO Rule 84AB brand-name registry entries for this brand stem
    stem = norm(p["name"]).split(" ")[0] if p.get("name") else None
    regs = maybe(cur, """SELECT firm_name, license_number, generic_name, brand_name FROM brand_registry
                         WHERE brand_norm = ? OR brand_norm LIKE ? ORDER BY (brand_norm = ?) DESC LIMIT 200""",
                 [stem, f"{stem} %", stem]) if stem and len(stem) >= 3 else []
    # same stem is not enough ("Dolo 650" vs "Dolo Gel"): the declared generic must name one of this product's molecules
    words = [norm(m["name"]).split(" ")[0][:6] for m in p["molecules"] if m.get("name")]
    p["brand_registry"] = [r for r in regs if any(w and w in norm(r["generic_name"] or "") for w in words)][:15] if words else regs[:15]
    # government procurement benchmark: tenders for exactly these molecules
    if mids:
        conds = " AND ".join([has_mol()] * len(mids))
        p["procurement"] = procurement(cur, f"{conds} AND len(string_split(molecule_ids, ',')) = ?", [str(m) for m in mids] + [len(mids)], 40)
    else:
        p["procurement"] = []
    p["pharmacology"] = enrichment(cur, mids[0]) if len(mids) == 1 else None
    p["molecule_reference"] = molecule_reference(cur, mids, p.get("dosage_form")) if not info else None
    return cleanrows([p])[0]


@router.get("/products/{pid}/live")
async def product_live(pid: int):
    """Live DrugSetu record (current MRP per pack, safety profile); cached 14 days, quota-aware."""
    from fastapi.concurrency import run_in_threadpool
    from ...connectors.drugsetu import lookup
    row = await run_in_threadpool(lookup, pid)
    if not row:
        return {"found": False}
    for k in ("safety", "raw"):
        if isinstance(row.get(k), str):
            row[k] = json.loads(row[k])
    raw = row.pop("raw", {}) or {}
    row["packagings"] = raw.get("packagings", [])
    row["how_it_works"] = raw.get("how_it_works")
    row["missed_dose"] = raw.get("missed_dose")
    return {"found": True, **cleanrows([row])[0]}


FORM_FAMILY = {
    "tablet": ("tablet",), "capsule": ("capsule",), "injection": ("injection", "infusion", "vial"),
    "syrup": ("syrup", "suspension", "oral solution", "oral liquid", "elixir"), "suspension": ("suspension", "syrup", "oral"),
    "cream": ("cream",), "gel": ("gel",), "ointment": ("ointment",), "drop": ("drop",), "eye drops": ("drop",),
    "lotion": ("lotion",), "powder": ("powder", "sachet", "granules"), "inhaler": ("inhal",), "solution": ("solution",),
}


def jan_aushadhi_for(cur, mids: list[int], n: int, strengths: list[str] | None = None, form: str | None = None) -> list[dict]:
    """PMBI generics with the same molecules; when strengths/form are given they must match too."""
    import re
    if not mids:
        return []
    conds = " AND ".join(["list_contains(string_split(molecule_ids, ','), ?)"] * len(mids))
    rows = db.rows(cur, f"""
        SELECT drug_code, name, unit_size, mrp, group_name FROM jan_aushadhi
        WHERE {conds} AND len(string_split(molecule_ids, ',')) = ? AND mrp > 0 ORDER BY mrp LIMIT 60""", [str(m) for m in mids] + [n])
    nums = [re.findall(r"\d+(?:\.\d+)?", s or "") for s in (strengths or [])]
    nums = [x[0] for x in nums if x]
    fam = FORM_FAMILY.get((form or "").strip().lower())
    out = []
    for r in rows:
        name = r["name"].lower()
        if nums and not all(re.search(rf"(?<![\d.]){re.escape(x)}(?![\d])", name) for x in nums):
            continue
        if fam and not any(w in name for w in fam):
            continue
        out.append(r)
    return out[:8]


# ------------------------------------------------------------------ combos (salt combinations)
@router.get("/combos")
def combos(q: str | None = None, molecule_id: int | None = None, therapeutic_class: str | None = None,
           banned: bool | None = None, min_brands: int = 1, sort: str = "brands", page: int = 1, limit: int = Query(50, le=500)):
    where, args = ["product_count >= ?"], [min_brands]
    if q:
        where.append("lower(label) LIKE ?"); args.append(f"%{q.lower()}%")
    if molecule_id:
        where.append("id IN (SELECT DISTINCT p.combo_id FROM product_molecules pm JOIN products p ON p.id = pm.product_id WHERE pm.molecule_id = ?)")
        args.append(molecule_id)
    if therapeutic_class:
        where.append("therapeutic_class = ?"); args.append(therapeutic_class)
    if banned is not None:
        where.append("coalesce(banned_skus, 0) > 0" if banned else "coalesce(banned_skus, 0) = 0")
    order = {"brands": "product_count DESC", "spread": "(max_unit / nullif(min_unit, 0)) DESC NULLS LAST",
             "companies": "company_count DESC", "median": "median_unit DESC NULLS LAST"}.get(sort, "product_count DESC")
    w = " AND ".join(where)
    cur = db.cursor()
    total = cur.execute(f"SELECT count(*) FROM combos WHERE {w}", args).fetchone()[0]
    data = db.rows(cur, f"""
        SELECT c.*, s.hhi, s.leader_share,
               coalesce(pa.name, co.name) AS leader
        FROM (SELECT * FROM combos WHERE {w} ORDER BY {order} LIMIT ? OFFSET ?) c
        LEFT JOIN segment_stats s ON s.segment_type = 'combo' AND s.segment = CAST(c.id AS VARCHAR)
        LEFT JOIN parents pa ON s.leader LIKE 'parent:%' AND pa.id = CAST(split_part(s.leader, ':', 2) AS INT)
        LEFT JOIN companies co ON s.leader LIKE 'company:%' AND co.id = CAST(split_part(s.leader, ':', 2) AS INT)
        ORDER BY {order.replace('product_count', 'c.product_count')}""", args + [limit, (page - 1) * limit])
    return paged(total, page, limit, data)


@router.get("/combos/{cid}")
def combo(cid: int):
    cur = db.cursor()
    c = db.one(cur, "SELECT * FROM combos WHERE id = ?", [cid])
    if not c:
        raise HTTPException(404, "combo not found")
    c["molecules"] = db.rows(cur, """
        SELECT DISTINCT m.id, m.name, pm.strength, m.nppa_ceiling, m.action_class FROM molecules m
        JOIN product_molecules pm ON pm.molecule_id = m.id
        WHERE pm.product_id = (SELECT min(id) FROM products WHERE combo_id = ?)""", [cid])
    c["brands"] = db.rows(cur, f"SELECT {PRODUCT_COLS} {PRODUCT_FROM} WHERE p.combo_id = ? ORDER BY coalesce(p.unit_price, p.mrp) ASC NULLS LAST LIMIT 400", [cid])
    c["share"] = share_table(cur, "combo", str(cid))
    c["stats"] = db.one(cur, "SELECT * FROM segment_stats WHERE segment_type='combo' AND segment = ?", [str(cid)])
    c["ban"] = db.rows(cur, "SELECT combo_text, notification, notified_on, status, source_url FROM reg_banned_fdc WHERE mkey = ?", [c["mkey"]])
    mids = [m["id"] for m in c["molecules"]]
    fam = {"oral liquid": "syrup", "topical": None, "unspecified": None, "eye/ear drops": "drop",
           "powder/granules": "powder"}.get(c.get("form_family"), c.get("form_family"))
    c["jan_aushadhi"] = jan_aushadhi_for(cur, mids, len(mids), [m["strength"] for m in c["molecules"]], fam)
    c["procurement"] = procurement(cur, " AND ".join([has_mol()] * len(mids)) + " AND len(string_split(molecule_ids, ',')) = ?",
                                   [str(m) for m in mids] + [len(mids)]) if mids else []
    c["related"] = db.rows(cur, """SELECT id, label, product_count, min_mrp, median_mrp FROM combos
                                   WHERE mkey = ? AND id <> ? ORDER BY product_count DESC LIMIT 20""", [c["mkey"], cid])
    return cleanrows([c])[0]


def share_table(cur, seg_type: str, seg: str, limit: int = 25) -> list[dict]:
    return db.rows(cur, """
        SELECT s.owner_type, s.owner_id, s.skus, s.value_share, s.breadth_share, s.rank,
               CASE WHEN s.owner_type = 'parent' THEN pa.name ELSE co.name END AS name,
               CASE WHEN s.owner_type = 'parent' THEN pa.slug ELSE co.slug END AS slug,
               pa.ticker
        FROM segment_share s
        LEFT JOIN parents pa ON s.owner_type = 'parent' AND pa.id = s.owner_id
        LEFT JOIN companies co ON s.owner_type = 'company' AND co.id = s.owner_id
        WHERE s.segment_type = ? AND s.segment = ? ORDER BY s.rank LIMIT ?""", [seg_type, seg, limit])


# ------------------------------------------------------------------ molecules
@router.get("/molecules")
def molecules(q: str | None = None, therapeutic_class: str | None = None, nlem: bool | None = None,
              controlled: bool | None = None, sort: str = "products", page: int = 1, limit: int = Query(50, le=500)):
    where, args = ["coalesce(m.product_count, 0) > 0"], []
    if q:
        where.append("m.mkey LIKE ?"); args.append(f"%{norm(q)}%")
    if therapeutic_class:
        where.append("m.therapeutic_class = ?"); args.append(therapeutic_class)
    if nlem is not None:
        where.append("coalesce(m.is_nlem, false) = ?"); args.append(nlem)
    if controlled is not None:
        where.append("(m.nppa_ceiling IS NOT NULL) = ?"); args.append(controlled)
    order = {"products": "m.product_count DESC", "companies": "m.company_count DESC", "name": "m.name",
             "hhi": "s.hhi DESC NULLS LAST", "combos": "m.combo_count DESC"}.get(sort, "m.product_count DESC")
    w = " AND ".join(where)
    cur = db.cursor()
    total = cur.execute(f"SELECT count(*) FROM molecules m WHERE {w}", args).fetchone()[0]
    data = db.rows(cur, f"""
        SELECT m.*, s.hhi, s.leader_share, coalesce(pa.name, co.name) AS leader
        FROM (SELECT m.* FROM molecules m LEFT JOIN segment_stats s ON s.segment_type = 'molecule' AND s.segment = CAST(m.id AS VARCHAR)
              WHERE {w} ORDER BY {order} LIMIT ? OFFSET ?) m
        LEFT JOIN segment_stats s ON s.segment_type = 'molecule' AND s.segment = CAST(m.id AS VARCHAR)
        LEFT JOIN parents pa ON s.leader LIKE 'parent:%' AND pa.id = CAST(split_part(s.leader, ':', 2) AS INT)
        LEFT JOIN companies co ON s.leader LIKE 'company:%' AND co.id = CAST(split_part(s.leader, ':', 2) AS INT)
        ORDER BY {order}""", args + [limit, (page - 1) * limit])
    return paged(total, page, limit, data)


@router.get("/molecules/{mid}")
def molecule(mid: int):
    cur = db.cursor()
    m = db.one(cur, "SELECT * FROM molecules WHERE id = ?", [mid])
    if not m:
        raise HTTPException(404, "molecule not found")
    m["combos"] = db.rows(cur, """
        SELECT k.id, k.label, k.molecule_count, k.product_count, k.company_count, k.min_mrp, k.median_mrp, k.max_mrp, k.is_banned, k.banned_skus
        FROM combos k WHERE k.id IN (SELECT DISTINCT p.combo_id FROM product_molecules pm JOIN products p ON p.id = pm.product_id WHERE pm.molecule_id = ?)
        ORDER BY k.product_count DESC LIMIT 60""", [mid])
    m["share"] = share_table(cur, "molecule", str(mid))
    m["stats"] = db.one(cur, "SELECT * FROM segment_stats WHERE segment_type='molecule' AND segment = ?", [str(mid)])
    m["nppa_ceiling"] = db.rows(cur, "SELECT form_strength, ceiling_price, unit, notification, year, source FROM nppa_ceiling WHERE molecule_id = ? ORDER BY year DESC", [mid])
    m["jan_aushadhi"] = db.rows(cur, "SELECT drug_code, name, unit_size, mrp, group_name FROM jan_aushadhi WHERE list_contains(string_split(molecule_ids, ','), ?) AND mrp > 0 ORDER BY mrp LIMIT 20", [str(mid)])
    m["nsq"] = db.rows(cur, """SELECT alert_month, category, product_text, batch_no, manufacturer, reason, lab, source_url
                               FROM reg_nsq WHERE list_contains(string_split(molecule_ids, ','), ?) ORDER BY alert_month DESC NULLS LAST LIMIT 50""", [str(mid)])
    m["bans"] = db.rows(cur, "SELECT combo_text, notification, notified_on, status FROM reg_banned_fdc WHERE list_contains(string_split(mkey, '|'), ?) ORDER BY notified_on DESC NULLS LAST", [m["mkey"]])
    m["shortages"] = db.rows(cur, "SELECT region, molecule_text, company, status, reason, updated_on, source FROM shortages WHERE list_contains(string_split(molecule_ids, ','), ?) ORDER BY updated_on DESC NULLS LAST LIMIT 20", [str(mid)])
    m["news"] = db.rows(cur, "SELECT id, published_at, source, title, url, topic FROM news WHERE list_contains(string_split(molecule_ids, ','), ?) ORDER BY published_at DESC LIMIT 15", [str(mid)])
    m["nlem"] = db.rows(cur, "SELECT section, level, dosage FROM nlem WHERE molecule_id = ?", [mid])
    m["approvals"] = db.rows(cur, """SELECT drug_text, indication, approved_on, source_url FROM reg_approvals
                                     WHERE list_contains(string_split(molecule_ids, ','), ?) ORDER BY approved_on DESC NULLS LAST LIMIT 20""", [str(mid)])
    m["sec"] = db.rows(cur, """SELECT meeting_date, committee, division, drug_text, firm, outcome, source_url FROM sec_items
                               WHERE list_contains(string_split(molecule_ids, ','), ?) ORDER BY meeting_date DESC LIMIT 40""", [str(mid)])
    m["trials"] = db.rows(cur, """SELECT nct_id, ctri_id, title, sponsor, phase, status, india_sites, last_update FROM trials
                                  WHERE list_contains(string_split(molecule_ids, ','), ?) ORDER BY last_update DESC LIMIT 30""", [str(mid)])
    m["forms"] = db.rows(cur, """SELECT p.dosage_form, count(*) n, median(p.mrp) median_mrp FROM products p
                                 JOIN product_molecules pm ON pm.product_id = p.id WHERE pm.molecule_id = ? AND p.dosage_form IS NOT NULL
                                 GROUP BY 1 ORDER BY 2 DESC LIMIT 12""", [mid])
    k = str(mid)
    m["pharmacology"] = enrichment(cur, mid)
    m["pvpi"] = maybe(cur, f"""SELECT issue_month, drug_text, reaction, indication, source_url FROM pvpi_alerts
                               WHERE {has_mol()} ORDER BY issue_month DESC""", [k])
    m["ceiling_history"] = maybe(cur, """SELECT year, form_strength, ceiling_price, unit, notification FROM nppa_ceiling_history
                                         WHERE molecule_id = ? ORDER BY lower(form_strength), year""", [mid])
    m["debarments"] = maybe(cur, f"""SELECT state, firm, drug_text, reason, ordered_on, years, document_url FROM firm_debarments
                                     WHERE {has_mol()} ORDER BY ordered_on DESC NULLS LAST LIMIT 30""", [k])
    m["procurement"] = procurement(cur, has_mol(), [k])
    m["global"] = {
        "us_applications": maybe(cur, f"""SELECT a.application_number, a.sponsor, a.app_type, a.brands, a.dosage_forms, a.marketing_status,
                                                 a.first_approval, a.last_action, pa.name AS parent, pa.slug AS parent_slug
                                          FROM us_applications a LEFT JOIN parents pa ON pa.id = a.parent_id
                                          WHERE {has_mol('a.molecule_ids')} ORDER BY (a.parent_id IS NOT NULL) DESC, a.last_action DESC NULLS LAST LIMIT 60""", [k]),
        "us_patents": maybe(cur, f"""SELECT application_number, kind, code, use_code, expires_on, ingredients FROM us_patents
                                     WHERE {has_mol()} AND (expires_on IS NULL OR expires_on >= current_date) ORDER BY expires_on LIMIT 40""", [k]),
        "us_ndc": (maybe(cur, f"""SELECT count(*) n, count(DISTINCT labeler) labelers, count(*) FILTER (WHERE parent_id IS NOT NULL) indian_group_ndcs,
                                         list(DISTINCT pa.name) FILTER (WHERE pa.name IS NOT NULL) indian_groups
                                  FROM us_ndc u LEFT JOIN parents pa ON pa.id = u.parent_id WHERE {has_mol('u.molecule_ids')}""", [k]) or [None])[0],
        "who_pq": maybe(cur, f"""SELECT ref, inn, applicant, dosage_form, therapeutic_area, basis, prequalified_on FROM who_pq
                                 WHERE {has_mol()} ORDER BY prequalified_on DESC NULLS LAST LIMIT 30""", [k]),
        "ema": maybe(cur, f"SELECT * FROM ema_medicines WHERE {has_mol()} LIMIT 20", [k]),
    }
    m["cdci"] = maybe(cur, """SELECT identifier, substance_name, cas_number, unii, molecular_formula, molecular_weight, iupac_name,
                                     substance_description, toxicity FROM cdci_substance WHERE molecule_id = ? LIMIT 3""", [mid])
    m["cdci_generics"] = maybe(cur, """SELECT generic_name, therapeutic_role, classification_of_drugs, indication, contra_indication, interaction_with_drugs
                                       FROM cdci_generic WHERE list_contains(string_split(substance_identifier, '+'), ?)
                                       ORDER BY (indication IS NULL), length(generic_name) LIMIT 25""", [m["cdci"][0]["identifier"]]) if m["cdci"] else []
    m["brand_registry_count"] = (maybe(cur, "SELECT count(*) n, count(DISTINCT firm_name) firms FROM brand_registry WHERE generic_name ILIKE ?",
                                       [f"%{m['name']}%"]) or [None])[0]
    return cleanrows([m])[0]


# ------------------------------------------------------------------ companies & parent groups
@router.get("/companies")
def companies(q: str | None = None, parent_id: int | None = None, sort: str = "products",
              page: int = 1, limit: int = Query(50, le=500)):
    where, args = ["coalesce(c.product_count, 0) > 0"], []
    if q:
        where.append("c.name_norm LIKE ?"); args.append(f"%{norm(q)}%")
    if parent_id:
        where.append("c.parent_id = ?"); args.append(parent_id)
    order = {"products": "c.product_count DESC", "molecules": "c.molecule_count DESC", "name": "c.name",
             "median": "c.median_mrp DESC NULLS LAST"}.get(sort, "c.product_count DESC")
    w = " AND ".join(where)
    cur = db.cursor()
    total = cur.execute(f"SELECT count(*) FROM companies c WHERE {w}", args).fetchone()[0]
    data = db.rows(cur, f"""
        SELECT c.*, pa.name AS parent, pa.slug AS parent_slug,
               (SELECT count(*) FROM reg_nsq n WHERE n.company_id = c.id) AS nsq_count
        FROM companies c LEFT JOIN parents pa ON pa.id = c.parent_id
        WHERE {w} ORDER BY {order} LIMIT ? OFFSET ?""", args + [limit, (page - 1) * limit])
    return paged(total, page, limit, data)


@router.get("/companies/{slug}")
def company(slug: str):
    cur = db.cursor()
    c = db.one(cur, "SELECT c.*, pa.name parent, pa.slug parent_slug FROM companies c LEFT JOIN parents pa ON pa.id = c.parent_id WHERE c.slug = ?", [slug])
    if not c:
        raise HTTPException(404, "company not found")
    return cleanrows([dossier(cur, "company", c["id"], c)])[0]


@router.get("/parents")
def parents():
    cur = db.cursor()
    data = db.rows(cur, """
        SELECT pa.*, q.price, q.change_pct, q.market_cap, q.pe, q.week52_high, q.week52_low,
               agg.companies, agg.products, agg.active, agg.molecules,
               (SELECT count(*) FROM reg_nsq n JOIN companies c2 ON c2.id = n.company_id WHERE c2.parent_id = pa.id) AS nsq_count,
               (SELECT count(*) FROM usfda_actions u WHERE u.parent_id = pa.id) AS usfda_count
        FROM parents pa
        LEFT JOIN quotes q ON q.ticker = pa.ticker || '.NS'
        LEFT JOIN (SELECT c.parent_id, count(DISTINCT c.id) companies, sum(c.product_count) products,
                          sum(c.active_count) active, max(c.molecule_count) molecules
                   FROM companies c WHERE c.parent_id IS NOT NULL GROUP BY 1) agg ON agg.parent_id = pa.id
        ORDER BY agg.products DESC NULLS LAST""")
    return {"data": cleanrows(data)}


@router.get("/parents/{slug}")
def parent(slug: str):
    cur = db.cursor()
    p = db.one(cur, """SELECT pa.*, q.price, q.change_pct, q.prev_close, q.day_high, q.day_low, q.volume, q.market_cap,
                              q.pe, q.week52_high, q.week52_low, q.quoted_at
                       FROM parents pa LEFT JOIN quotes q ON q.ticker = pa.ticker || '.NS' WHERE pa.slug = ?""", [slug])
    if not p:
        raise HTTPException(404, "group not found")
    p["subsidiaries"] = db.rows(cur, "SELECT id, slug, name, product_count, active_count, molecule_count FROM companies WHERE parent_id = ? ORDER BY product_count DESC NULLS LAST", [p["id"]])
    p["history"] = db.rows(cur, "SELECT d, close, volume FROM quote_history WHERE ticker = ? ORDER BY d", [f"{p['ticker']}.NS"]) if p["ticker"] else []
    p["usfda"] = db.rows(cur, "SELECT kind, firm, subject, issued_on, url FROM usfda_actions WHERE parent_id = ? ORDER BY issued_on DESC LIMIT 30", [p["id"]])
    p["news"] = db.rows(cur, "SELECT id, published_at, source, title, url, topic FROM news WHERE list_contains(string_split(parent_ids, ','), ?) ORDER BY published_at DESC LIMIT 30", [str(p["id"])])
    p["sec"] = db.rows(cur, """SELECT meeting_date, committee, division, drug_text, outcome, source_url FROM sec_items
                               WHERE parent_id = ? ORDER BY meeting_date DESC LIMIT 40""", [p["id"]])
    p["trials"] = db.rows(cur, """SELECT nct_id, ctri_id, title, phase, status, india_sites, last_update FROM trials
                                  WHERE parent_id = ? ORDER BY last_update DESC LIMIT 40""", [p["id"]])
    p["filings"] = maybe(cur, """SELECT announced_at, category, text, attachment, topic FROM corp_announcements
                                 WHERE parent_id = ? ORDER BY announced_at DESC LIMIT 60""", [p["id"]])
    p["us_portfolio"] = (maybe(cur, """SELECT count(*) applications, count(*) FILTER (WHERE app_type = 'ANDA') andas,
                                              count(*) FILTER (WHERE app_type = 'NDA') ndas, count(*) FILTER (WHERE app_type = 'BLA') blas,
                                              max(last_action) last_action FROM us_applications WHERE parent_id = ?""", [p["id"]]) or [None])[0]
    p["us_recent"] = maybe(cur, """SELECT application_number, app_type, brands, ingredients, dosage_forms, marketing_status, first_approval, last_action
                                   FROM us_applications WHERE parent_id = ? ORDER BY last_action DESC NULLS LAST LIMIT 25""", [p["id"]])
    p["us_ndc_count"] = (maybe(cur, "SELECT count(*) n FROM us_ndc WHERE parent_id = ?", [p["id"]]) or [{"n": 0}])[0]["n"]
    p["who_pq"] = maybe(cur, """SELECT ref, inn, dosage_form, therapeutic_area, prequalified_on FROM who_pq
                                WHERE parent_id = ? ORDER BY prequalified_on DESC NULLS LAST LIMIT 30""", [p["id"]])
    return cleanrows([dossier(cur, "parent", p["id"], p)])[0]


def dossier(cur, owner_type: str, owner_id: int, base: dict) -> dict:
    """Portfolio + share + quality record shared by company and parent pages."""
    comp_filter = "c.parent_id = ?" if owner_type == "parent" else "c.id = ?"
    base["portfolio"] = db.rows(cur, f"""
        SELECT p.therapeutic_class, count(*) skus, count(DISTINCT p.combo_id) combos, median(p.mrp) median_mrp,
               count(*) FILTER (WHERE p.in_stock) in_stock
        FROM products p JOIN companies c ON c.id = p.company_id
        WHERE {comp_filter} AND coalesce(p.is_discontinued, false) = false
        GROUP BY 1 ORDER BY 2 DESC""", [owner_id])
    base["class_share"] = db.rows(cur, """
        SELECT s.segment, s.skus, s.value_share, s.breadth_share, s.rank, st.owners, st.hhi
        FROM segment_share s JOIN segment_stats st USING (segment_type, segment)
        WHERE s.segment_type = 'class' AND s.owner_type = ? AND s.owner_id = ? ORDER BY s.w DESC""", [owner_type, owner_id])
    base["top_molecules"] = db.rows(cur, """
        SELECT m.id, m.name, s.skus, s.value_share, s.rank, st.owners
        FROM segment_share s JOIN segment_stats st USING (segment_type, segment)
        JOIN molecules m ON CAST(m.id AS VARCHAR) = s.segment
        WHERE s.segment_type = 'molecule' AND s.owner_type = ? AND s.owner_id = ?
        ORDER BY s.w DESC LIMIT 30""", [owner_type, owner_id])
    base["leadership"] = db.rows(cur, """
        SELECT k.id, k.label, s.skus, s.value_share, st.owners, k.product_count
        FROM segment_share s JOIN segment_stats st USING (segment_type, segment)
        JOIN combos k ON CAST(k.id AS VARCHAR) = s.segment
        WHERE s.segment_type = 'combo' AND s.owner_type = ? AND s.owner_id = ? AND s.rank = 1 AND st.owners >= 5
        ORDER BY k.product_count DESC LIMIT 25""", [owner_type, owner_id])
    base["top_brands"] = db.rows(cur, f"""
        SELECT {PRODUCT_COLS} {PRODUCT_FROM}
        WHERE {comp_filter.replace('c.', 'c.')} AND p.mrp IS NOT NULL
        ORDER BY p.source_count DESC, p.mrp DESC LIMIT 40""", [owner_id])
    base["nsq"] = db.rows(cur, f"""
        SELECT n.alert_month, n.category, n.product_text, n.batch_no, n.manufacturer, n.reason, n.lab, n.source_url
        FROM reg_nsq n JOIN companies c ON c.id = n.company_id WHERE {comp_filter}
        ORDER BY n.alert_month DESC NULLS LAST LIMIT 50""", [owner_id])
    base["banned_skus"] = db.rows(cur, f"""
        SELECT p.id, p.name, p.mrp, p.ban_level, k.label FROM products p JOIN companies c ON c.id = p.company_id
        LEFT JOIN combos k ON k.id = p.combo_id WHERE {comp_filter} AND p.ban_level IS NOT NULL
        AND coalesce(p.is_discontinued, false) = false ORDER BY p.ban_level, p.name LIMIT 100""", [owner_id])
    base["tenders"] = maybe(cur, f"""
        SELECT r.buyer, r.item, r.unit, r.rate, r.level, r.order_share, r.tender_no, r.valid_to, r.category
        FROM procurement_rates r JOIN companies c ON c.id = r.company_id WHERE {comp_filter}
        ORDER BY (r.level = 'L1') DESC, r.buyer, r.item LIMIT 80""", [owner_id])
    base["debarments"] = maybe(cur, f"""
        SELECT d.state, d.authority, d.drug_text, d.reason, d.order_no, d.ordered_on, d.years, d.document_url
        FROM firm_debarments d JOIN companies c ON c.id = d.company_id WHERE {comp_filter}
        ORDER BY d.ordered_on DESC NULLS LAST LIMIT 40""", [owner_id])
    base["licences"] = maybe(cur, f"""
        SELECT b.license_number, count(*) brands, any_value(b.firm_name) firm
        FROM brand_registry b JOIN companies c ON c.id = b.company_id WHERE {comp_filter}
        GROUP BY 1 ORDER BY 2 DESC LIMIT 40""", [owner_id])
    return base
