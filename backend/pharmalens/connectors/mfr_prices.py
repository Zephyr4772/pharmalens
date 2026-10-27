"""Manufacturers' statutory price lists: current MRP, PTR and PTS per pack, straight from the company.

DPCO 2013 para 24 obliges every manufacturer to issue a price list (Form V) to dealers, State Drug Controllers and
the government, and to re-issue it on every revision; after the September 2025 GST cut most large companies issued
complete revised lists. Sources, in order: lists published on manufacturers' own websites, then the index of
manufacturers' Form V documents that NPPA asked e-pharmacies to display (only those PDFs are read, never the
e-pharmacy's own catalogue). Each PDF is parsed once; rows are matched to catalog products strictly (same corporate
group, same brand and strength, same or cleanly divisible pack, price within 3x of what we had) and newer prices
update the catalog.
"""
import io
import re
from datetime import date, datetime
from urllib.parse import unquote, urljoin

import pandas as pd
import pdfplumber

from .. import db, matcher
from ..normalize import norm
from .base import Connector

NETMEDS_INDEX = "https://www.netmeds.com/page/nppa-circulars"
COMPANY_PAGES = {   # manufacturers that link their current list from their own site: page scanned for price-list PDFs
    "Ipca Laboratories": "https://www.ipca.com/",
}
GST_CUT = date(2025, 9, 22)


# ------------------------------------------------------------------ parsing
def num(s) -> float | None:
    """'1 ,920.00' / '9 7.83' (PDF kerning splits digits) -> float."""
    s = re.sub(r"[\s,₹]|Rs\.?", "", str(s or ""))
    m = re.fullmatch(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def _txt(c) -> str:
    return re.sub(r"\s+", " ", str(c or "").replace("\n", " ")).strip()


OLD_MARK = re.compile(r"\bold\b|pre[- ]?revised|pre gst|before|upto|up to|existing")
NEW_MARK = re.compile(r"\bnew\b|(?<!pre-)(?<!pre )revised|\bfrom\b|effective|w\.?e\.?f|post gst|after")
MRP_HEAD = re.compile(r"\bmrp\b|maximum retail|retail price \(incl")


def classify(headers: list[str], inherited: list[str] | None = None, above: list[str] | None = None) -> dict | None:
    """Column roles from header text. `inherited` is the group title above each column (merged header cells);
    a column's own words decide old vs new MRP, the group title only when unambiguous, else position."""
    h = [x.lower() for x in headers]
    up = [x.lower() for x in (inherited or [""] * len(h))]
    # an MRP column says so itself, or sits under an MRP group title with only a before/after label of its own
    # ("Maximum Retail Price" over "Before 22/09/2025" | "From 22/09/2025"); a banner above "Product Name" is not one
    mrp_cols = [i for i, x in enumerate(h)
                if (MRP_HEAD.search(x) or (MRP_HEAD.search(up[i]) and (OLD_MARK.search(x) or NEW_MARK.search(x))))
                and "reduction" not in x and not re.search(r"\bptr\b|\bpts\b|price to", x)
                and not ("gst" in x and not MRP_HEAD.search(x))]     # 'GST rate' is not a price; 'MRP (incl GST)' is
    if not mrp_cols:
        return None
    side = {}
    for i in mrp_cols:
        o, n = OLD_MARK.search(h[i]), NEW_MARK.search(h[i])
        if o and not n:
            side[i] = "old"
        elif n and not o:
            side[i] = "new"
        else:
            o, n = OLD_MARK.search(up[i]), NEW_MARK.search(up[i])
            side[i] = "old" if o and not n else "new" if n and not o else None
    for i in mrp_cols:   # no usable wording: the first MRP column is the old price, the last the new
        if side[i] is None:
            side[i] = "old" if i == mrp_cols[0] and len(mrp_cols) > 1 else "new"
    new = [i for i in mrp_cols if side[i] == "new"] or mrp_cols[-1:]
    old = [i for i in mrp_cols if side[i] == "old" and i not in new]
    # 'new MRP per pack' beats 'per strip'; a per-strip price is flagged so the pack is read per strip
    per_pack = [i for i in new if "pack" in h[i]]
    pick = per_pack[-1] if per_pack else new[-1]
    roles = {"mrp": pick, "per_strip": bool(re.search(r"strip", h[pick]))}
    if old:
        roles["mrp_old"] = old[0]
    direct = [x.lower() for x in (above or [""] * len(h))]
    for i, x in enumerate(h):
        if i in mrp_cols:
            continue
        x = x or direct[i]          # 'Item Name' can sit a header row higher than the price headers
        if "product" not in roles and re.search(r"product name|product description|name of the product|name of the formulation|formulation name|"
                                                r"material description|material name|^product$|brand|^description|item name|^sku", x) \
                and not re.search(r"code|type|division|category|group", x):
            roles["product"] = i
        elif "composition" not in roles and "composition" in x:
            roles["composition"] = i
        elif "pack" not in roles and re.search(r"\bpack", x) and "price" not in x:
            roles["pack"] = i
        elif "code" not in roles and "code" in x and "hsn" not in x:
            roles["code"] = i
        elif re.search(r"\bptr\b|price to retailer", x):
            roles["ptr"] = i                      # last one wins: the revised PTR
        elif re.search(r"\bpts\b|price to (stockist|distributor)", x):
            roles["pts"] = i
        elif re.search(r"\bgst\b", x) and "slab change" not in x and "hsn" not in x:
            roles["gst"] = i
        elif "status" not in roles and re.search(r"product type|status", x):
            roles["status"] = i
    return roles if "product" in roles else None


def parse_pdf(content: bytes) -> list[dict]:
    rows, roles = [], None
    layouts: dict[int, dict] = {}   # column layout per column count: one document can mix table widths
    carry = None                    # a product name cut by a page break: its first half ends the previous table
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                prev: list[str] = []
                tail = None
                for raw in table:
                    cells = [_txt(c) for c in raw]
                    # headers span rows and merged cells ("Maximum Retail Price" over "Before" / "From"):
                    # each column inherits the nearest group title to its left in the row above
                    above, last = [], ""
                    for c in (prev if len(prev) == len(cells) else [""] * len(cells)):
                        last = c or last
                        above.append(last)
                    r = classify(cells, above, prev if len(prev) == len(cells) else None)
                    if r and not any(num(c) is not None and len(c) > 3 for c in cells[1:]):
                        roles = layouts[len(cells)] = r
                        prev = cells
                        continue
                    prev = cells
                    # tables continue across pages without the header: reuse the layout of the same width
                    use = layouts.get(len(cells)) or roles
                    if not use or len(cells) <= max(v for k, v in use.items() if k != "per_strip"):
                        continue
                    roles = use
                    product = cells[roles["product"]]
                    mrp = num(cells[roles["mrp"]])
                    if product and mrp is None and num(product) is None:
                        tail = product          # no price on this line: maybe the top half of a split row
                        continue
                    tail = None
                    if not product or mrp is None or mrp <= 0 or num(product) is not None or re.fullmatch(r"\(\d+\)", product):
                        continue
                    if carry:
                        product, carry = f"{carry} {product}", None
                    get = lambda k: cells[roles[k]] if k in roles else None
                    gst = num((get("gst") or "").replace("%", ""))
                    rows.append({"product": product, "composition": get("composition"), "pack": get("pack"),
                                 "per_strip": roles["per_strip"], "code": get("code"), "mrp": mrp,
                                 "mrp_old": num(get("mrp_old")) or None, "ptr": num(get("ptr")), "pts": num(get("pts")),
                                 "gst": round(gst * 100, 2) if gst is not None and gst < 1 else gst, "status": get("status")})
                carry = tail            # only a priceless line that ends a table continues on the next page
    return rows


# ------------------------------------------------------------------ documents
def doc_meta(title: str, url: str) -> dict:
    """Company and effective date from the document's title / file name."""
    name = unquote(url.rsplit("/", 1)[-1]).rsplit(".", 1)[0]
    t = f"{title} {name}"
    eff = None
    m = re.search(r"(\d{1,2})[-./](\d{1,2})[-./](20\d\d)", t)
    if m:
        try:
            eff = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            eff = None
    if not eff:
        m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-_ ]*(20\d\d)", t, re.I)
        if m:
            eff = datetime.strptime(f"1 {m.group(1)[:3]} {m.group(2)}", "%d %b %Y").date()
    if not eff and re.search(r"gst", t, re.I):
        eff = GST_CUT
    label = re.sub(r"(?i)form[-_ ]?v\b|price\s*list|pricelist|new\s*gst|revised|supplementary|of all|domestic formulations|"
                   r"scheduled formulations|applicable|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-_ ]*20\d\d|"
                   r"\d{1,2}[-./]\d{1,2}[-./]20\d\d|\b20\d\d\b|\b\d\b|[-_]+", " ", name)
    return {"label": re.sub(r"\s+", " ", label).strip(" -"), "effective_on": eff}


def is_price_list(name: str) -> bool:
    n = unquote(name).lower()
    return bool(re.search(r"form[-_ ]?v\b|price\s*list|pricelist", n)) and not re.search(r"s\.?\s*o\.?\s*\d|corrigendum|wpi|\bcp\b|cp-", n)


# ------------------------------------------------------------------ matching
FORM_WORDS = (r"tablets?|tabs?|capsules?|caps?|syrup|syp|suspension|susp|injection|inj|infusion|ointment|oint|cream|cr|gel|lotion|"
              r"drops?|sachets?|powder|pdr|solution|soln|spray|inhaler|respules?|rotacaps?|vial|bottle|strip|tube|ampoule|amp|"
              r"sale|dt|kit|pack|box|units?|nos?|bag|pen|cartridge|softgels?|granules?|lozenges?|shampoo|soap|liquid|oral|"
              r"film coated|fc|t")
UNITS = r"mg|mcg|gm|g|ml|iu|kg|w w|w v|v v"


def name_key(name: str) -> str:
    """Brand + strength without pack, form and unit words: 'AB - FLO SR TAB (10X10)' -> 'abflosr'."""
    s = re.sub(r"\s+\d+\(\d+\.\d+\s*[A-Za-z]+\).*$", " ", name or "")   # Form V 'Calchek 2.5 Mg Tablet 10(10.00 No)'
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\b\d+\s*[xX*]\s*\d+.*$", " ", s)                # trailing '10 X 10' pack
    s = re.sub(r"\b\d+\s*'?s\b", " ", s, flags=re.I)              # '10s', "15's"
    s = re.sub(r"\b\d+(?:\.\d+)?\s*(?:gm|g|ml|kg|ltr|l)\s*$", " ", s.strip(), flags=re.I)   # 'Cream 15gm': tube size, not strength
    s = re.sub(r"(\d)([a-zA-Z])", r"\1 \2", norm(s))                # '200mg' -> '200 mg'
    s = re.sub(rf"\b({FORM_WORDS})\b", " ", s)
    s = re.sub(rf"\b({UNITS})\b", " ", s)
    return re.sub(r"[^a-z0-9]", "", s)


def list_pack_qty(pack: str | None, product: str = "", per_strip: bool = False) -> float | None:
    """'10 X 10 T' -> 100 (5 when priced per strip of '40 X 5'), 'STRIP 15s' -> 15, '20 GM' -> 20, '10.00 No' -> 10."""
    for text, is_pack in ((pack or "", True), (product or "", False)):
        m = re.search(r"(\d+(?:\.\d+)?)\s*[xX*]\s*(\d+(?:\.\d+)?)(?:\s*[xX*]\s*(\d+(?:\.\d+)?))?", text)
        if m:
            nums = [float(g) for g in m.groups() if g]
            if per_strip:
                return nums[-1]
            q = 1.0
            for n in nums:
                q *= n
            return q
        # in the pack column '10 TABLET' / '20 GM' is a count; in a product name '40 Tab' is a strength,
        # so names only count "15's" / '(10.00 No)'-style quantities
        unit = r"'?s\b|no\b|nos\b|tab|cap|gm\b|g\b|ml\b|bag|vial|amp|sachet|strip" if is_pack else r"'s\b|s\b(?!\w)|\.00\s*(?:no|tablet|capsule|ml)"
        m = re.search(rf"(\d+(?:\.\d+)?)\s*(?:{unit})", text, re.I)
        if m:
            return float(m.group(1))
    return None


FORM_GROUPS = {   # dosage forms that are interchangeable for matching; different groups never match
    "oral_solid": r"tablet|tab\b|caplet|capsule|cap\b|softgel",
    "oral_liquid": r"syrup|syp\b|suspension|susp\b|liquid|elixir|oral solution|drops? oral|linctus|expectorant",
    "injection": r"injection|inj\b|vial|infusion|ampoule|amp\b|prefilled|pfs\b|cartridge|pen\b",
    "topical": r"cream|ointment|oint\b|gel\b|lotion|emulsion|paste|dusting powder",
    "eye_ear_nose": r"eye|ear|nasal|ophthalmic|otic",
    "soap_shampoo": r"soap|shampoo|wash|cleanser|bar\b",
    "inhaled": r"inhaler|respule|rotacap|nebuli|aerosol",
    "powder": r"sachet|granule|powder|pdr\b",
    "spray": r"spray",
}


def form_group(text: str) -> str | None:
    t = (text or "").lower()
    for g, pat in FORM_GROUPS.items():
        if re.search(pat, t):
            return g
    return None


class Matcher:
    """Catalog products of one corporate group, indexed by name key."""

    def __init__(self, cur, parent_id: int | None, company_id: int | None):
        self.by_key: dict[str, list[tuple]] = {}
        if parent_id:
            where, arg = "c.parent_id = ? OR p.company_id = ?", [parent_id, company_id or -1]
        elif company_id:
            # no corporate group: sister entities that share the distinctive name ('A. Menarini India' and
            # 'Menarini India' both sell Menarini brands); the brand + strength + form + pack checks still apply
            name = cur.execute("SELECT name FROM companies WHERE id = ?", [company_id]).fetchone()[0] or ""
            stem = next((w for w in norm(name).split() if len(w) >= 5 and w not in
                         {"india", "indian", "pharma", "pharmaceuticals", "private", "limited", "healthcare", "laboratories",
                          "lifesciences", "life", "sciences", "remedies", "biotech", "products", "international"}), None)
            where, arg = ("p.company_id = ? OR lower(c.name) LIKE ?", [company_id, f"%{stem}%"]) if stem \
                else ("p.company_id = ?", [company_id])
        else:
            return
        for pid, name, nn, qty, mrp, form, pack in cur.execute(f"""
                SELECT p.id, p.name, p.name_norm, p.pack_qty, p.mrp, p.dosage_form, p.pack_size
                FROM products p JOIN companies c ON c.id = p.company_id WHERE {where}""", arg).fetchall():
            self.by_key.setdefault(name_key(name), []).append(
                (pid, nn, qty, mrp, form_group(f"{form or ''} {name} {pack or ''}")))

    def match(self, row: dict) -> dict | None:
        key = name_key(row["product"])
        cands = self.by_key.get(key) if len(key) >= 4 else None
        if not cands:
            return None
        # same brand, different form ('Medisoft Soap' vs 'Medisoft Cream') is a different product
        lf = form_group(f"{row['product']} {row.get('pack') or ''} {row.get('composition') or ''}")
        if lf:
            cands = [c for c in cands if c[4] in (lf, None)]
        lq = list_pack_qty(row.get("pack"), row["product"], row.get("per_strip", False))
        exact = [c for c in cands if lq and c[2] and abs(c[2] - lq) < 1e-6]
        if len(exact) == 1:
            pid, nn, qty, old, _ = exact[0]
            kind, scale = "same_pack", 1.0
        elif not exact and len(cands) == 1:
            pid, nn, qty, old, _ = cands[0]
            if lq and qty and lq != qty:
                big, small = max(lq, qty), min(lq, qty)
                if abs(big / small - round(big / small)) > 1e-6:
                    return None                       # packs that do not divide cleanly: not the same product
                kind, scale = "scaled", qty / lq
            else:
                kind, scale = ("same_pack" if lq and qty else "name_only"), 1.0
        else:
            return None                               # ambiguous: several packs or several products
        pack_mrp = round(row["mrp"] * scale, 2)
        if old:
            # prices move by tax changes and yearly increments, not by multiples: compare like with like
            # (the list's own pre-revision MRP when it gives one) and treat a big gap as a different pack/product
            ref = row["mrp_old"] * scale if row.get("mrp_old") else pack_mrp
            if not (0.6 <= ref / old <= 1.6):
                return None
        return {"product_id": pid, "match_name": nn, "match_kind": kind, "pack_mrp": pack_mrp, "pack_qty": lq}


# ------------------------------------------------------------------ feed
def asof_date(s: str | None) -> date | None:
    """Comparable date of a catalog price vintage: '2022-24', '2025', 'drugsetu 2026-10-15', 'mfr 2025-09-22'."""
    if not s:
        return None
    m = re.search(r"(20\d\d)-(\d\d)-(\d\d)", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return {"2025": date(2025, 6, 30), "2022-24": date(2024, 8, 1)}.get(s.strip())


KIND_RANK = {"same_pack": 0, "scaled": 1, "name_only": 2}


def best_rows(w, product_ids: set[int] | None = None) -> dict[int, tuple]:
    """Newest manufacturer price per matched product; on the same date an exact pack beats a scaled one."""
    flt = f"AND product_id IN ({','.join(map(str, product_ids))})" if product_ids else ""
    best = {}
    for pid, nn, eff, pack_mrp, kind, pack, qty, label in w.execute(f"""
            SELECT product_id, match_name, effective_on, pack_mrp, match_kind, pack, pack_qty, company_label FROM mfr_prices
            WHERE product_id IS NOT NULL AND effective_on IS NOT NULL {flt}""").fetchall():
        rank = (eff, -KIND_RANK.get(kind, 9))
        if pid not in best or rank > best[pid][0]:
            best[pid] = (rank, nn, eff, pack_mrp, kind, pack, qty, label)
    return best


def apply_prices(w, product_ids: set[int] | None = None) -> int:
    """Put the best manufacturer price onto each catalog product when it is newer than what it has. Returns updates."""
    best = best_rows(w, product_ids)
    if not best:
        return 0
    current = {pid: (asof, pack, qty) for pid, asof, pack, qty in w.execute(
        f"SELECT id, mrp_asof, pack_size, pack_qty FROM products WHERE id IN ({','.join(map(str, best))})").fetchall()}
    obs, upd = [], []
    for pid, (_, _, eff, pack_mrp, kind, pack, qty, label) in best.items():
        if pid not in current:
            continue
        obs.append({"product_id": pid, "observed_on": eff, "mrp": pack_mrp, "source": f"mfr:{label}"[:60]})
        asof, pack_size, pack_qty = current[pid]
        have = asof_date(asof)
        if have and have > eff:
            continue
        if kind == "name_only" and not pack_qty and qty:
            # the manufacturer's own pack fills a gap, written the way the catalog build reads pack sizes
            pack_size, pack_qty = (f"pack of {qty:g} ({pack})" if pack else f"pack of {qty:g}"), qty
        upd.append({"id": pid, "mrp": pack_mrp, "mrp_asof": f"mfr {eff:%Y-%m-%d}", "pack_size": pack_size,
                    "pack_qty": pack_qty, "unit_price": round(pack_mrp / pack_qty, 4) if pack_qty else None})
    # set-based writes: per-row statements on keyed tables exhaust DuckDB's memory cap on the server
    w.register("_obs", pd.DataFrame(obs))
    w.execute("""INSERT OR IGNORE INTO price_observations
                 SELECT product_id::INTEGER, observed_on::DATE, mrp::DOUBLE, source FROM _obs""")
    w.unregister("_obs")
    if upd:
        w.register("_upd", pd.DataFrame(upd))
        w.execute("""UPDATE products SET mrp = u.mrp::DOUBLE, mrp_asof = u.mrp_asof, pack_size = u.pack_size,
                     pack_qty = u.pack_qty::DOUBLE, unit_price = u.unit_price::DOUBLE
                     FROM _upd u WHERE products.id = u.id::INTEGER""")
        w.unregister("_upd")
    return len(upd)


class MfrPriceLists(Connector):
    name = "mfr_price_lists"
    title = "Manufacturer Price Lists (Form V)"
    agency = "Manufacturers (DPCO Form V)"
    schedule = {"trigger": "cron", "day_of_week": "mon,thu", "hour": 12, "minute": 10}
    description = ("Manufacturers' statutory price lists (MRP, PTR, PTS per pack) from company websites and the Form V "
                   "index NPPA asked e-pharmacies to display; matched to catalog SKUs to keep MRPs current.")
    per_run = 25

    def _docs(self) -> list[dict]:
        docs = []
        for company, page in COMPANY_PAGES.items():
            try:
                html = self.get(page).text
                for href in sorted(set(re.findall(r'href="([^"]+\.pdf)"', html, re.I))):
                    if re.search(r"price-?list", href, re.I):
                        docs.append({"url": urljoin(page, href), "title": href.rsplit("/", 1)[-1], "label": company, "host": page})
            except Exception as e:  # noqa: BLE001
                self.stats.notes.append(f"{company} site: {str(e)[:80]}")
        try:
            html = self.get(NETMEDS_INDEX).text
            for href, text in re.findall(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', html, re.I | re.S):
                title = re.sub(r"<[^>]+>|\s+", " ", text).strip()
                if is_price_list(f"{title} {href.rsplit('/', 1)[-1]}"):
                    docs.append({"url": href, "title": title, "label": None, "host": "netmeds.com (manufacturer Form V index)"})
        except Exception as e:  # noqa: BLE001
            self.stats.notes.append(f"Form V index: {str(e)[:80]}")
        seen, out = set(), []
        for d in docs:
            if d["url"] not in seen:
                seen.add(d["url"])
                out.append(d)
        return out

    def run(self):
        docs = self._docs()
        cur = db.cursor()
        done = {r[0] for r in cur.execute("SELECT key FROM connector_state WHERE key LIKE 'mfrprice|%'").fetchall()}
        todo = [d for d in docs if f"mfrprice|{d['url']}" not in done]
        for d in todo:
            meta = doc_meta(d["title"], d["url"])
            d["effective_on"] = meta["effective_on"]
            d["label"] = d["label"] or meta["label"]
        todo.sort(key=lambda d: d["effective_on"] or date.min, reverse=True)
        todo = todo[: self.per_run]
        self.stats.notes.append(f"{len(docs)} price lists found, {len(todo)} to parse")
        touched: set[int] = set()
        for d in todo:
            try:
                r = self.get(d["url"], timeout=180)
                rows = parse_pdf(r.content) if r.status_code == 200 else []
            except Exception as e:  # noqa: BLE001 — one bad PDF must not stop the rest
                self.stats.notes.append(f"{d['label']}: {str(e)[:80]}")
                continue
            company_id, parent_id = matcher.company_for(d["label"]), matcher.parent_for(d["label"])
            if not parent_id and company_id:
                parent_id = cur.execute("SELECT parent_id FROM companies WHERE id = ?", [company_id]).fetchone()[0]
            m = Matcher(cur, parent_id, company_id)
            records = []
            for i, row in enumerate(rows):
                hit = m.match(row) or {}
                if hit:
                    touched.add(hit["product_id"])
                records.append({
                    "key": f"{d['url']}|{i}", "doc_url": d["url"], "doc_title": d["title"][:300], "doc_host": d["host"],
                    "company_label": d["label"], "parent_id": parent_id, "company_id": company_id,
                    "effective_on": d["effective_on"], "code": row.get("code"), "product": row["product"][:300],
                    "composition": (row.get("composition") or "")[:500] or None, "pack": row.get("pack"),
                    "pack_qty": hit.get("pack_qty") or list_pack_qty(row.get("pack"), row["product"], row.get("per_strip", False)),
                    "gst": row.get("gst"), "ptr": row.get("ptr"), "pts": row.get("pts"), "mrp_old": row.get("mrp_old"),
                    "mrp": row["mrp"], "status": row.get("status"), "product_id": hit.get("product_id"),
                    "match_name": hit.get("match_name"), "match_kind": hit.get("match_kind"), "pack_mrp": hit.get("pack_mrp")})
            matched = sum(1 for r in records if r["product_id"])
            with db.writer() as w:
                if records:
                    # one bulk insert per document: row-by-row inserts into a keyed table exhaust DuckDB's memory cap
                    df = pd.DataFrame(records)
                    for col in ("parent_id", "company_id", "product_id"):
                        df[col] = df[col].astype("Int64")
                    w.execute("DELETE FROM mfr_prices WHERE doc_url = ?", [d["url"]])
                    w.register("_mfr", df)
                    w.execute("""INSERT INTO mfr_prices SELECT key, doc_url, doc_title, doc_host, company_label,
                                 parent_id::INTEGER, company_id::INTEGER, effective_on::DATE, code, product, composition, pack,
                                 pack_qty::DOUBLE, gst::DOUBLE, ptr::DOUBLE, pts::DOUBLE, mrp_old::DOUBLE, mrp::DOUBLE, status,
                                 product_id::INTEGER, match_name, match_kind, pack_mrp::DOUBLE, now() FROM _mfr""")
                    w.unregister("_mfr")
                w.execute("INSERT OR REPLACE INTO connector_state VALUES (?, ?)",
                          [f"mfrprice|{d['url']}", f"{datetime.now().isoformat()}|{len(rows)}|{matched}"])
                if rows and d["effective_on"] and (date.today() - d["effective_on"]).days <= 45:
                    self.emit(w, kind="price_notification", severity="info", ts=d["effective_on"],
                              title=f"{d['label']} price list: {len(rows):,} products, {matched:,} matched to the catalog",
                              url=d["url"], dedupe_key=f"mfrprice|{d['url']}")
            self.stats.rows_seen += len(rows)
            self.stats.rows_new += matched
            if not company_id and not parent_id:
                self.stats.notes.append(f"unknown company '{d['label']}'")
        if touched:
            from ..derived import refresh_combo_prices
            with db.writer() as w:
                n = apply_prices(w, touched)
                refresh_combo_prices(w)
            self.stats.notes.append(f"{n:,} catalog MRPs updated")
        total = cur.execute("SELECT count(*), count(product_id) FROM mfr_prices").fetchone()
        self.stats.notes.append(f"{total[0]:,} list rows stored, {total[1]:,} matched")
