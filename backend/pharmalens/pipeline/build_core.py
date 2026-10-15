"""Build the core catalog into DuckDB.

Sources (all local, see data/sources):
  * Indian Medicine Master Dataset (Kaggle, built 2026-09-15): spine of ~543k products,
    medicine->molecule links, classes, uses, side effects, NPPA ceiling prices.
  * India Medicines and Drug Info Dataset (1mg scrape, 2025): newer MRPs, Rx flag,
    in-stock flag; adds products the master missed.
  * Legacy PharmaLens catalog (Aug 2024): CDSCO NSQ list + US FDA shortages baseline.

Core tables are dropped and rebuilt; live tables (events, reg_*, news, quotes, ...)
are untouched. Stop the API server before running (DuckDB single-writer).

    cd backend && py -3 -m pharmalens.pipeline.build_core
"""
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

import duckdb

from ..config import DB_PATH, LEGACY_DIR, MASTER_DIR, ONEMG_2025_CSV, SCHEMA_VERSION, SEED_DIR
from ..normalize import (
    molecule_key, norm, norm_company, norm_product, norm_strength, pack_quantity,
    parse_composition, slugify,
)

CORE_TABLES = [
    "parents", "companies", "molecules", "combos", "products",
    "product_molecules", "interactions", "nppa_ceiling", "build_meta",
]
LEGAL_TOKENS = {"pvt", "private", "ltd", "limited", "llp", "inc", "co", "corp", "the", "m", "s", "ms"}

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def log(msg: str):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def company_key(name: str) -> str:
    return " ".join(t for t in norm(name).split() if t not in LEGAL_TOKENS)


def display_name(raw: str, key: str) -> str:
    r = raw.strip()
    # raw carries scrape junk (strength digits, glued company) -> fall back to the cleaned key
    if re.search(r"\d", r) or re.search(r"\b(pvt|ltd|limited|llp)", r, re.I):
        return key.title()
    if r.isupper() or r.islower():
        return r.title()
    return r


def bulk_insert(con, table: str, cols: list[str], rows: list[tuple]):
    import pandas as pd
    df = pd.DataFrame(rows, columns=cols)
    con.register("_bulk", df)
    con.execute(f"INSERT INTO {table} ({', '.join(cols)}) SELECT {', '.join(cols)} FROM _bulk")
    con.unregister("_bulk")


GLUED_MFR = re.compile(r"^(.*?\b(?i:ltd|limited|llp|inc|pvt|private)\.?)(?=[A-Z][a-z]+.*\()")


def clean_mfr(raw: str | None) -> str | None:
    """'Morepen Laboratories LTDSitagliptin (100mg)' -> 'Morepen Laboratories LTD'."""
    if not raw:
        return raw
    m = GLUED_MFR.match(raw)
    return m.group(1).strip() if m else raw.strip()


FORM_FAMILIES = [
    ("injection", ("injection", "infusion", "vial", "ampoule", "prefilled", "pen", "cartridge")),
    ("inhalation", ("inhal", "respule", "rotacap", "nebul", "aerosol")),
    ("eye/ear drops", ("eye", "ear", "ophthalmic")),
    ("oral liquid", ("syrup", "suspension", "solution", "liquid", "drop", "linctus", "elixir", "emulsion", "expectorant")),
    ("topical", ("cream", "gel", "ointment", "lotion", "spray", "soap", "shampoo", "powder for", "dusting", "paste", "foam", "patch", "serum", "wash")),
    ("powder/granules", ("powder", "sachet", "granule")),
    ("capsule", ("capsule", "softgel")),
    ("tablet", ("tablet", "caplet")),
    ("suppository", ("suppositor", "pessar", "vaginal")),
]


def form_family(form: str | None, name: str) -> str:
    text = f"{form or ''} {name}".lower()
    for fam, words in FORM_FAMILIES:
        if any(w in (form or "").lower() for w in words):
            return fam
    for fam, words in FORM_FAMILIES:
        if any(w in text for w in words):
            return fam
    return "unspecified"


def to_bool(v):
    if v is None or v == "":
        return None
    s = str(v).strip().lower()
    if s in ("true", "yes", "1", "prescription required"):
        return True
    if s in ("false", "no", "0"):
        return False
    return None


def to_float(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- 2025 1mg parse
RX_MARK = "Prescription Required"
TAIL_MARKS = ("not available", "ADD")
MRP_RE = re.compile(r"MRP₹\s*([\d,]+(?:\.\d+)?)")
FORM_WORDS = sorted("""Injection Syrup Dry Oral Suspension Cream Eye Ear Nasal Drop Drops Tablet Tablets Capsule Capsules
    Powder Gel Infusion Ointment Soap Lotion Solution Spray Shampoo Inhaler Respules Sachet Sachets Granules Mouth Wash
    Face Rotacap Rotacaps Emulsion Paste Toothpaste Jelly Liquid Kit Patch Pen Cartridge Lozenges Suppository Pessary
    Vial Ampoule Serum Oil Tonic Linctus Elixir Softgel Softgels Chewable Effervescent Gargle Foam Dusting Prefilled
    Syringe Film Expectorant Gum Transcaps Redicaps Inhalation Topical Vaginal Rectal Sugar Free Drink Bar""".split(), key=len, reverse=True)
FORM_PREFIX = re.compile(r"^(?:(?:" + "|".join(FORM_WORDS) + r")(?:/| )?)+")
BOUNDARY_RE = re.compile(r"(?<=[a-z\.\)])(?=[A-Z])")


def parse_onemg_2025(known_mfrs: list[str]) -> dict[str, dict]:
    """Return {name_norm: record}. The scrape glued fields together, e.g.
    'Abixim 100mg TabletMRP₹87.47Prescription Requiredstrip of 10 tabletsAbbottCefixime (100mg)not available'."""
    by_len = sorted({m.strip() for m in known_mfrs if m and len(m.strip()) > 2}, key=len, reverse=True)
    PFX = 5
    by_prefix = defaultdict(list)  # first PFX chars -> candidates, longest first
    short = []
    for m in by_len:
        (by_prefix[m[:PFX]] if len(m) >= PFX else short).append(m)

    out: dict[str, dict] = {}
    with open(ONEMG_2025_CSV, encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            name = (row.get("Medicine Name") or "").strip()
            blob = row.get("Product Name") or ""
            if not name or not blob.startswith(name):
                continue
            rest = blob[len(name):]
            mrp = None
            m = MRP_RE.match(rest)
            if m:
                mrp = to_float(m.group(1).replace(",", ""))
                rest = rest[m.end():]
            rx = None
            if rest.startswith(RX_MARK):
                rx, rest = True, rest[len(RX_MARK):]
            in_stock = None
            for t in TAIL_MARKS:
                if rest.endswith(t):
                    in_stock = t == "ADD"
                    rest = rest[: -len(t)]
                    break
            # pack = leading run without capitals ("strip of 10 tablets"), plus a trailing
            # capitalised form word when the pack ends in a count ("bottle of 100 ml Syrup")
            pm = re.match(r"^([^A-Z]*?)(?=[A-Z]|$)", rest)
            pack = pm.group(1) if pm else ""
            rest = rest[len(pack):]
            fm = FORM_PREFIX.match(rest)
            if fm and re.search(r"(\d|ml|gm|g|of)\s*$", pack):
                pack, rest = pack + fm.group(0), rest[fm.end():]
            pack = pack.strip()
            mfr, comp = None, None
            for cand in by_prefix.get(rest[:PFX], []) + short:
                if rest.startswith(cand):
                    mfr, comp = cand, rest[len(cand):]
                    break
            if mfr is None:
                b = BOUNDARY_RE.search(rest)
                if b:
                    mfr, comp = rest[: b.start()], rest[b.start():]
                else:
                    mfr, comp = rest, ""
            key = norm_product(name)
            if key in out:
                continue
            out[key] = {
                "name": name, "mrp": mrp, "rx": rx if rx else (False if row.get("Is Prescription Required?") == "False" else rx),
                "pack": pack or None, "mfr": (mfr or "").strip() or None, "comp": (comp or "").strip() or None,
                "in_stock": in_stock, "image": row.get("Image URL") or None,
            }
    return out


# ---------------------------------------------------------------- main build
def build():
    t0 = time.time()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    for t in CORE_TABLES:
        con.execute(f"DROP TABLE IF EXISTS {t}")
    con.execute((SEED_DIR.parent / "schema.sql").read_text())

    M = str(MASTER_DIR).replace("\\", "/") + "/"
    log("loading master dataset")
    con.execute(f"CREATE OR REPLACE TEMP TABLE m AS SELECT * FROM read_csv_auto('{M}medicines.csv', sample_size=-1)")
    con.execute(f"CREATE OR REPLACE TEMP TABLE mm AS SELECT * FROM read_csv_auto('{M}medicine_molecules.csv', sample_size=-1)")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE mf AS
        SELECT medicine_id,
               coalesce(manufacturer, manufacturer_apollo, marketer_ndj, manufacturer_1mg, manufacturer_mh, company_ru, marketer) AS mfr,
               manufacturer_netmeds AS indication_group
        FROM '{M}medicines_full.parquet'""")
    con.execute("UPDATE m SET manufacturer = mf.mfr FROM mf WHERE mf.medicine_id = m.medicine_id")
    indication = dict(con.execute("SELECT medicine_id, indication_group FROM mf WHERE indication_group IS NOT NULL").fetchall())
    master_rows = con.execute(
        """SELECT medicine_id, medicine_name, manufacturer, dosage_form, pack_size, price_inr,
                  is_discontinued, prescription, composition, therapeutic_class, action_class,
                  chemical_class, habit_forming, uses, side_effects, image_url, source_count
           FROM m"""
    ).fetchall()
    log(f"master rows: {len(master_rows):,}")

    known_mfrs = [r[0] for r in con.execute("SELECT DISTINCT manufacturer FROM m WHERE manufacturer IS NOT NULL").fetchall()]
    log("parsing 2025 1mg scrape")
    onemg = parse_onemg_2025(known_mfrs)
    log(f"2025 rows parsed: {len(onemg):,}")

    # ---- products
    products = []  # dict rows
    by_norm: dict[str, int] = {}
    src_to_pid: dict[str, int] = {}
    matched_2025 = 0
    for (mid, name, mfr, form, pack, price, disc, rx, comp, tclass, aclass, cclass,
         habit, uses, se, img, scount) in master_rows:
        if not name:
            continue
        key = norm_product(name)
        if key in by_norm:
            continue
        pid = len(products) + 1
        o = onemg.get(key)
        mrp_old = to_float(price)
        rec = {
            "id": pid, "src_id": mid, "name": name, "name_norm": key,
            "manufacturer_raw": clean_mfr(mfr or (o and o["mfr"])), "dosage_form": form, "pack_size": pack or (o and o["pack"]),
            "mrp": mrp_old, "mrp_asof": "2022-24" if mrp_old else None, "mrp_legacy": mrp_old,
            "composition": comp or (o and o["comp"]),
            "rx_required": to_bool(rx), "is_discontinued": to_bool(disc), "in_stock": None,
            "therapeutic_class": tclass, "action_class": aclass, "chemical_class": cclass,
            "habit_forming": to_bool(habit), "uses": uses, "side_effects": se,
            "image_url": img, "source_count": scount or 0, "sources": "master",
            "indication_group": indication.get(mid),
        }
        if o:
            matched_2025 += 1
            if o["mrp"]:
                rec["mrp"], rec["mrp_asof"] = o["mrp"], "2025"
            if o["rx"] is not None:
                rec["rx_required"] = o["rx"]
            rec["in_stock"] = o["in_stock"]
            rec["image_url"] = rec["image_url"] or o["image"]
            rec["sources"] = "master,1mg-2025"
            rec["source_count"] += 1
            o["_used"] = True
        products.append(rec)
        by_norm[key] = pid
        src_to_pid[mid] = pid

    added_2025 = 0
    for key, o in onemg.items():
        if o.get("_used") or key in by_norm:
            continue
        pid = len(products) + 1
        products.append({
            "id": pid, "src_id": None, "name": o["name"], "name_norm": key,
            "manufacturer_raw": clean_mfr(o["mfr"]), "dosage_form": None, "pack_size": o["pack"],
            "mrp": o["mrp"], "mrp_asof": "2025" if o["mrp"] else None, "mrp_legacy": None,
            "composition": o["comp"], "rx_required": o["rx"], "is_discontinued": None,
            "in_stock": o["in_stock"], "therapeutic_class": None, "action_class": None,
            "chemical_class": None, "habit_forming": None, "uses": None, "side_effects": None,
            "image_url": o["image"], "source_count": 1, "sources": "1mg-2025",
        })
        by_norm[key] = pid
        added_2025 += 1
    log(f"products: {len(products):,} (2025 matched {matched_2025:,}, 2025-only added {added_2025:,})")

    # dosage form fallback from name
    FORMS = ["tablet", "capsule", "syrup", "suspension", "injection", "cream", "gel", "ointment", "drop",
             "lotion", "powder", "solution", "inhaler", "respules", "spray", "soap", "shampoo", "sachet",
             "infusion", "lozenge", "granules", "patch", "suppository", "kit", "emulsion", "paste", "rotacap"]
    for p in products:
        n = p["name_norm"]
        df = (p["dosage_form"] or "").lower()
        # some sources put the whole glued pack/maker string in the form column ("strip of 10 tablet srblair remedies")
        if df and (len(df) > 30 or re.search(r"\b(strip|bottle|tube|vial|box|packet) of\b", df)):
            p["dosage_form"] = None
        if not p["dosage_form"] or p["dosage_form"].lower() in ("allopathy", "ayurvedic", "homeopathy", "unani"):
            for fm in FORMS:
                if f" {fm}" in f" {n}":
                    p["dosage_form"] = fm.title()
                    break
        if p["dosage_form"]:
            p["dosage_form"] = p["dosage_form"].strip().title()
        q, _ = pack_quantity(p["pack_size"])
        p["pack_qty"] = q
        p["unit_price"] = round(p["mrp"] / q, 4) if (p["mrp"] and q) else None

    # ---- molecules + links
    log("linking molecules")
    mol_by_key: dict[str, dict] = {}
    links: list[tuple[int, str, str]] = []  # (pid, mkey, strength)
    for mid, molecule, strength in con.execute("SELECT medicine_id, molecule, strength FROM mm").fetchall():
        pid = src_to_pid.get(mid)
        k = molecule_key(molecule)
        if not pid or not k:
            continue
        mol_by_key.setdefault(k, {"name": display_name(molecule, k)})
        links.append((pid, k, norm_strength(strength)))
    linked = {l[0] for l in links}
    for p in products:
        if p["id"] in linked:
            continue
        o = onemg.get(p["name_norm"])
        comp = (o and o["comp"]) or p["composition"]
        if not comp:
            continue
        for molname, strength in parse_composition(comp):
            k = molecule_key(molname)
            if not k or len(k) < 3:
                continue
            mol_by_key.setdefault(k, {"name": display_name(molname, k)})
            links.append((p["id"], k, norm_strength(strength)))
    # dedupe links per product
    seen = set()
    uniq_links = []
    for l in links:
        if (l[0], l[1]) in seen:
            continue
        seen.add((l[0], l[1]))
        uniq_links.append(l)
    links = uniq_links
    mol_ids = {k: i + 1 for i, k in enumerate(sorted(mol_by_key))}
    log(f"molecules: {len(mol_ids):,}, links: {len(links):,}")

    # ---- combos
    per_product = defaultdict(list)
    for pid, k, s in links:
        per_product[pid].append((k, s))
    combo_ids: dict[str, int] = {}
    combo_meta: dict[str, dict] = {}
    prod_by_id = {p["id"]: p for p in products}
    for pid, parts in per_product.items():
        parts.sort()
        p0 = prod_by_id[pid]
        fam = form_family(p0["dosage_form"], p0["name_norm"])
        # same molecules + strengths + dosage-form family = genuinely substitutable products
        ckey = "|".join(f"{k}:{s}" for k, s in parts) + f"#{fam}"
        if ckey not in combo_ids:
            combo_ids[ckey] = len(combo_ids) + 1
            combo_meta[ckey] = {
                "mkey": "|".join(k for k, _ in parts),
                "label": " + ".join(f"{mol_by_key[k]['name']}{(' ' + s) if s else ''}" for k, s in parts)
                         + (f" · {fam}" if fam != "unspecified" else ""),
                "n": len(parts), "fam": fam,
            }
        p = prod_by_id[pid]
        p["combo_id"] = combo_ids[ckey]
        p["molecule_count"] = len(parts)

    # ---- class propagation: molecule class = mode of its products' classes
    mol_class = defaultdict(Counter)
    mol_aclass = defaultdict(Counter)
    mol_cclass = defaultdict(Counter)
    for pid, k, _ in links:
        p = prod_by_id[pid]
        if p["therapeutic_class"]:
            mol_class[k][p["therapeutic_class"]] += 1
        if p["action_class"] and p.get("molecule_count") == 1:
            mol_aclass[k][p["action_class"]] += 1
        if p["chemical_class"] and p.get("molecule_count") == 1:
            mol_cclass[k][p["chemical_class"]] += 1
    filled = 0
    for pid, parts in per_product.items():
        p = prod_by_id[pid]
        if not p["therapeutic_class"]:
            for k, _ in parts:
                if mol_class[k]:
                    p["therapeutic_class"] = mol_class[k].most_common(1)[0][0]
                    filled += 1
                    break
        if not p["action_class"] and len(parts) == 1 and mol_aclass[parts[0][0]]:
            p["action_class"] = mol_aclass[parts[0][0]].most_common(1)[0][0]
    log(f"therapeutic class propagated to {filled:,} products")

    # ---- parents + companies
    log("resolving companies")
    parents_seed = json.loads((SEED_DIR / "parents.json").read_text(encoding="utf-8"))
    parent_rx = [(i + 1, [re.compile(pt) for pt in p["patterns"]]) for i, p in enumerate(parents_seed)]
    companies: dict[str, dict] = {}
    for p in products:
        raw = p["manufacturer_raw"]
        if not raw:
            p["company_id"] = None
            continue
        ck = company_key(raw)
        if not ck:
            p["company_id"] = None
            continue
        c = companies.get(ck)
        if c is None:
            heavy = norm_company(raw)
            parent_id = None
            for pid_, rxs in parent_rx:
                if any(r.search(heavy) or r.search(ck) for r in rxs):
                    parent_id = pid_
                    break
            c = {"id": len(companies) + 1, "name": raw.strip(), "name_norm": ck, "parent_id": parent_id, "names": Counter()}
            companies[ck] = c
        c["names"][raw.strip()] += 1
        p["company_id"] = c["id"]
    slugs = set()
    for c in companies.values():
        c["name"] = c["names"].most_common(1)[0][0]
        s = slugify(c["name"])
        if s in slugs:
            s = f"{s}-{c['id']}"
        slugs.add(s)
        c["slug"] = s
    log(f"companies: {len(companies):,}; with parent: {sum(1 for c in companies.values() if c['parent_id']):,}")

    # ---- write tables
    log("writing tables")
    bulk_insert(con, "parents", ["id", "slug", "name", "ticker", "hq", "ownership", "notes"],
        [(i + 1, slugify(p["name"]), p["name"], p["ticker"], p["hq"], p["ownership"], p.get("notes")) for i, p in enumerate(parents_seed)],
    )
    bulk_insert(con, "companies", ["id", "slug", "name", "name_norm", "parent_id"],
        [(c["id"], c["slug"], c["name"], c["name_norm"], c["parent_id"]) for c in companies.values()],
    )
    bulk_insert(con, "molecules", ["id", "mkey", "name", "action_class", "chemical_class", "therapeutic_class"],
        [
            (mol_ids[k], k, v["name"],
             mol_aclass[k].most_common(1)[0][0] if mol_aclass[k] else None,
             mol_cclass[k].most_common(1)[0][0] if mol_cclass[k] else None,
             mol_class[k].most_common(1)[0][0] if mol_class[k] else None)
            for k, v in mol_by_key.items()
        ],
    )
    bulk_insert(con, "combos", ["id", "ckey", "mkey", "label", "molecule_count", "form_family"],
        [(cid, ck, combo_meta[ck]["mkey"], combo_meta[ck]["label"], combo_meta[ck]["n"], combo_meta[ck]["fam"]) for ck, cid in combo_ids.items()],
    )

    cols = ["id", "src_id", "name", "name_norm", "company_id", "manufacturer_raw", "dosage_form", "pack_size",
            "pack_qty", "mrp", "mrp_asof", "mrp_legacy", "unit_price", "composition", "combo_id", "molecule_count",
            "rx_required", "is_discontinued", "in_stock", "therapeutic_class", "action_class", "chemical_class",
            "habit_forming", "uses", "side_effects", "image_url", "source_count", "sources", "indication_group"]
    import pandas as pd
    df = pd.DataFrame([{c: p.get(c) for c in cols} for p in products], columns=cols)
    con.register("df_products", df)
    con.execute(f"INSERT INTO products ({', '.join(cols)}) SELECT {', '.join(cols)} FROM df_products")
    con.unregister("df_products")
    del df

    ldf = pd.DataFrame([(pid, mol_ids[k], s) for pid, k, s in links], columns=["product_id", "molecule_id", "strength"])
    con.register("df_links", ldf)
    con.execute("INSERT INTO product_molecules SELECT * FROM df_links")
    con.unregister("df_links")

    con.execute(
        f"""INSERT INTO interactions
            SELECT p.id, d.drug_interactions_raw
            FROM read_csv_auto('{M}drug_interactions.csv', sample_size=-1) d
            JOIN products p ON p.src_id = d.medicine_id"""
    )

    # NPPA ceiling prices (master copy; live connector appends newer notifications)
    nppa = con.execute(
        f"SELECT sno, year, molecule_name, dosage_form_strength, notification, ceiling_price_inr, unit FROM read_csv_auto('{M}nppa_ceiling_prices.csv', sample_size=-1)"
    ).fetchall()
    bulk_insert(con, "nppa_ceiling", ["id", "molecule_id", "molecule_name", "form_strength", "ceiling_price", "unit", "notification", "year", "source"],
        [(i + 1, mol_ids.get(molecule_key(n)), n, fs, cp, u, nt, y, "kaggle:syedahmadrayyan/nppa")
         for i, (sno, y, n, fs, nt, cp, u) in enumerate(nppa)],
    )

    # ---- rollups
    log("computing rollups")
    con.execute("""
        UPDATE molecules SET
          product_count = s.pc, company_count = s.cc, combo_count = s.kc
        FROM (SELECT pm.molecule_id, count(*) pc, count(DISTINCT p.company_id) cc, count(DISTINCT p.combo_id) kc
              FROM product_molecules pm JOIN products p ON p.id = pm.product_id GROUP BY 1) s
        WHERE molecules.id = s.molecule_id""")
    con.execute("""
        UPDATE molecules SET nppa_ceiling = s.cp
        FROM (SELECT molecule_id, min(ceiling_price) cp FROM nppa_ceiling WHERE molecule_id IS NOT NULL GROUP BY 1) s
        WHERE molecules.id = s.molecule_id""")
    con.execute("""
        UPDATE combos SET
          product_count = s.pc, company_count = s.cc, min_mrp = s.mn, median_mrp = s.md, max_mrp = s.mx,
          therapeutic_class = s.tc
        FROM (SELECT combo_id, count(*) pc, count(DISTINCT company_id) cc,
                     min(mrp) mn, median(mrp) md, max(mrp) mx, mode(therapeutic_class) tc
              FROM products WHERE combo_id IS NOT NULL GROUP BY 1) s
        WHERE combos.id = s.combo_id""")
    con.execute("""
        UPDATE combos SET min_unit = s.mn, median_unit = s.md, max_unit = s.mx
        FROM (SELECT p.combo_id, min(p.unit_price) mn, median(p.unit_price) md, max(p.unit_price) mx
              FROM products p
              JOIN (SELECT combo_id, median(unit_price) med FROM products WHERE unit_price > 0 GROUP BY 1) m USING (combo_id)
              WHERE p.unit_price >= 0.15 * m.med AND p.unit_price <= 20 * m.med
              GROUP BY 1) s
        WHERE combos.id = s.combo_id""")
    con.execute("""
        UPDATE companies SET
          product_count = s.pc, active_count = s.ac, molecule_count = s.mc, median_mrp = s.md, top_class = s.tc
        FROM (SELECT p.company_id, count(*) pc,
                     count(*) FILTER (WHERE coalesce(p.is_discontinued, false) = false) ac,
                     count(DISTINCT pm.molecule_id) mc, median(p.mrp) md, mode(p.therapeutic_class) tc
              FROM products p LEFT JOIN product_molecules pm ON pm.product_id = p.id
              WHERE p.company_id IS NOT NULL GROUP BY 1) s
        WHERE companies.id = s.company_id""")

    # baseline price observations
    con.execute("""INSERT OR IGNORE INTO price_observations
                   SELECT id, DATE '2025-06-30', mrp, '1mg-2025' FROM products WHERE mrp_asof = '2025' AND mrp IS NOT NULL""")
    con.execute("""INSERT OR IGNORE INTO price_observations
                   SELECT id, DATE '2024-08-01', mrp_legacy, 'catalog-2022-24' FROM products WHERE mrp_legacy IS NOT NULL""")

    load_legacy_regulatory(con, mol_ids)

    # indexes for API latency
    for sql in [
        "CREATE INDEX IF NOT EXISTS ix_prod_norm ON products(name_norm)",
        "CREATE INDEX IF NOT EXISTS ix_prod_company ON products(company_id)",
        "CREATE INDEX IF NOT EXISTS ix_prod_combo ON products(combo_id)",
        "CREATE INDEX IF NOT EXISTS ix_pm_mol ON product_molecules(molecule_id)",
        "CREATE INDEX IF NOT EXISTS ix_pm_prod ON product_molecules(product_id)",
        "CREATE INDEX IF NOT EXISTS ix_comp_parent ON companies(parent_id)",
        "CREATE INDEX IF NOT EXISTS ix_combo_mkey ON combos(mkey)",
    ]:
        con.execute(sql)

    stats = con.execute("""SELECT
        (SELECT count(*) FROM products), (SELECT count(*) FROM products WHERE mrp IS NOT NULL),
        (SELECT count(*) FROM products WHERE mrp_asof='2025'), (SELECT count(*) FROM molecules),
        (SELECT count(*) FROM combos), (SELECT count(*) FROM companies), (SELECT count(*) FROM parents),
        (SELECT count(*) FROM products WHERE combo_id IS NOT NULL)""").fetchone()
    meta = {
        "schema_version": SCHEMA_VERSION,
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "products": stats[0], "products_priced": stats[1], "products_priced_2025": stats[2],
        "molecules": stats[3], "combos": stats[4], "companies": stats[5], "parents": stats[6],
        "products_with_composition": stats[7],
        "sources": "Indian Medicine Master Dataset (Kaggle, 2026-09); 1mg 2025 scrape (Kaggle apkaayush); legacy PharmaLens 2024",
        "build_seconds": round(time.time() - t0, 1),
    }
    con.executemany("INSERT INTO build_meta VALUES (?, ?)", [(k, str(v)) for k, v in meta.items()])
    con.execute("CHECKPOINT")
    con.close()
    log(json.dumps(meta, indent=1))


def load_legacy_regulatory(con, mol_ids):
    """Baseline from the 2024 project: CDSCO NSQ batch list + US FDA shortage list.
    Live connectors append to the same tables."""
    now = datetime.now()
    nsq_path = LEGACY_DIR / "bad_actors.json"
    if nsq_path.exists():
        rows = json.loads(nsq_path.read_text(encoding="utf-8"))
        ins = []
        for r in rows:
            name = r.get("Name of Drugs/medical device/cosmetics") or ""
            bm = r.get("Batch No./Date of Manufacture/Date of Expiry/Manufactured By") or ""
            batch = re.search(r"B\.?\s*No\.?\s*[:\-]?\s*([^,]+)", bm, re.I)
            mfgd = re.search(r"Mfg\.?\s*dt\.?\s*[:\-]?\s*([^,]+)", bm, re.I)
            expd = re.search(r"Exp\.?\s*dt\.?\s*[:\-]?\s*([^,]+)", bm, re.I)
            mfr = re.search(r"M(?:fd|anufactured)\.?\s*by\s*[:\-]?\s*(.+)$", bm, re.I)
            key = norm(f"legacy|{name}|{batch.group(1) if batch else bm}")
            ins.append((
                None, "NSQ", name.strip(), batch.group(1).strip() if batch else None,
                mfgd.group(1).strip() if mfgd else None, expd.group(1).strip() if expd else None,
                mfr.group(1).strip() if mfr else None, (r.get("Reason for failure") or "").strip(),
                r.get("Drawn By"), r.get("From"), "legacy:bad_actors.json", key, now,
            ))
        con.executemany(
            """INSERT OR IGNORE INTO reg_nsq (alert_month, category, product_text, batch_no, mfg_date, exp_date,
               manufacturer, reason, drawn_by, lab, source_url, dedupe_key, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", ins)
    sh_path = LEGACY_DIR / "shortages.json"
    if sh_path.exists():
        rows = json.loads(sh_path.read_text(encoding="utf-8"))
        ins = []
        for i, r in enumerate(rows):
            r = {k.strip(): v for k, v in r.items()}
            gen = r.get("Generic Name") or ""
            d = r.get("Date of Update")
            try:
                d = datetime.strptime(d, "%m/%d/%Y").date() if d else None
            except ValueError:
                d = None
            mids = sorted({str(mol_ids[k]) for k in (molecule_key(x) for x in re.split(r"[;,]", gen.split(" Tablet")[0])) if k in mol_ids})
            ins.append((f"usfda-{i}", "US", gen, r.get("Company Name"), r.get("Status"), r.get("Reason for Shortage"),
                        r.get("Therapeutic Category"), d, "US FDA Drug Shortages (legacy snapshot)", ",".join(mids) or None))
        con.executemany("INSERT OR IGNORE INTO shortages VALUES (?,?,?,?,?,?,?,?,?,?)", ins)


if __name__ == "__main__":
    build()
