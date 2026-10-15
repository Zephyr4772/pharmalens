"""SHELF: check an inventory list against bans, NSQ/spurious batches, recalls, price caps and cheaper equivalents."""
import csv
import io
import re
from datetime import date, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from rapidfuzz import fuzz

from ... import db
from ...normalize import norm
from ..common import cleanrows
from .catalog import jan_aushadhi_for

router = APIRouter(prefix="/shelf", tags=["shelf"])


class Item(BaseModel):
    name: str
    batch: str | None = None
    qty: float | None = None
    expiry: str | None = None
    manufacturer: str | None = None


class CheckRequest(BaseModel):
    rows: list[Item] | None = None
    csv: str | None = None


HEADER_ALIASES = {
    "name": ("name", "product", "product name", "item", "item name", "brand", "drug", "medicine", "description"),
    "batch": ("batch", "batch no", "batch number", "lot", "batch_no"),
    "qty": ("qty", "quantity", "stock", "units", "closing stock"),
    "expiry": ("expiry", "exp", "expiry date", "exp date", "exp_date"),
    "manufacturer": ("manufacturer", "company", "mfr", "mfg by", "marketed by"),
}


def parse_csv(text: str) -> list[Item]:
    rdr = csv.reader(io.StringIO(text.strip()))
    rows = [r for r in rdr if any(c.strip() for c in r)]
    if not rows:
        return []
    head = [norm(c) for c in rows[0]]
    cols = {}
    for key, aliases in HEADER_ALIASES.items():
        for i, h in enumerate(head):
            if h in aliases:
                cols[key] = i
                break
    body = rows[1:] if "name" in cols else rows
    if "name" not in cols:
        cols = {"name": 0, "batch": 1, "qty": 2, "expiry": 3}
    out = []
    for r in body:
        g = lambda k: (r[cols[k]].strip() if k in cols and cols[k] < len(r) else None) or None  # noqa: E731
        if not g("name"):
            continue
        q = g("qty")
        try:
            qv = float(q.replace(",", "")) if q else None
        except ValueError:
            qv = None
        out.append(Item(name=g("name"), batch=g("batch"), qty=qv, expiry=g("expiry"), manufacturer=g("manufacturer")))
    return out[:2000]


def parse_expiry(s: str | None) -> date | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%m/%Y", "%m-%Y", "%m/%y", "%m-%y", "%b-%Y", "%b %Y", "%b-%y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m"):
        try:
            d = datetime.strptime(s, fmt).date()
            if fmt in ("%m/%Y", "%m-%Y", "%m/%y", "%m-%y", "%b-%Y", "%b %Y", "%b-%y", "%Y-%m"):
                # expiry printed as month means end of that month
                nm = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
                return date.fromordinal(nm.toordinal() - 1)
            return d
        except ValueError:
            continue
    return None


def match_product(cur, name: str, manufacturer: str | None):
    n = norm(name)
    exact = cur.execute("SELECT id FROM products WHERE name_norm = ? ORDER BY source_count DESC LIMIT 1", [n]).fetchone()
    if exact:
        return exact[0], 100.0
    toks = n.split()
    if not toks:
        return None, 0
    cands = cur.execute("""SELECT p.id, p.name_norm, c.name_norm FROM products p LEFT JOIN companies c ON c.id = p.company_id
                           WHERE p.name_norm LIKE ? LIMIT 400""", [toks[0] + "%"]).fetchall()
    best, score = None, 0.0
    mf = norm(manufacturer) if manufacturer else ""
    for pid, pn, cn in cands:
        s = fuzz.token_set_ratio(n, pn) * 0.85 + fuzz.ratio(n, pn) * 0.15
        if mf and cn and fuzz.partial_ratio(mf, cn) > 80:
            s += 5
        if s > score:
            best, score = pid, s
    return (best, round(score, 1)) if score >= 72 else (None, round(score, 1))


@router.post("/check")
def check(req: CheckRequest):
    items = list(req.rows or [])
    if req.csv:
        items += parse_csv(req.csv)
    if not items:
        raise HTTPException(400, "send rows[] or csv")
    if len(items) > 2000:
        items = items[:2000]
    cur = db.cursor()
    today = date.today()
    results, counts = [], {"critical": 0, "warning": 0, "info": 0, "ok": 0, "unmatched": 0}
    for it in items:
        flags = []
        pid, score = match_product(cur, it.name, it.manufacturer)
        prod = None
        if pid:
            prod = db.one(cur, """SELECT p.id, p.name, p.mrp, p.unit_price, p.pack_size, p.combo_id, p.molecule_count,
                                         p.is_discontinued, p.company_id, c.name company, c.parent_id, p.ban_level, p.ban_id, k.label combo_label
                                  FROM products p LEFT JOIN companies c ON c.id = p.company_id LEFT JOIN combos k ON k.id = p.combo_id
                                  WHERE p.id = ?""", [pid])
        # batch-level NSQ / spurious hit (works even without a catalog match)
        if it.batch:
            b = re.sub(r"\s+", "", it.batch).upper()
            for r in db.rows(cur, """SELECT category, product_text, batch_no, manufacturer, reason, alert_month, source_url, company_id
                                      FROM reg_nsq WHERE upper(replace(batch_no, ' ', '')) = ?""", [b]):
                same = fuzz.token_set_ratio(norm(it.name), norm(r["product_text"])) >= 55 or (prod and r["company_id"] == prod["company_id"])
                if same:
                    flags.append({"level": "critical", "code": "SPURIOUS_BATCH" if r["category"] == "SPURIOUS" else "NSQ_BATCH",
                                  "message": f"Batch {r['batch_no']} declared {'SPURIOUS' if r['category'] == 'SPURIOUS' else 'Not of Standard Quality'} "
                                             f"({r['alert_month']}): {r['reason'] or ''}. Quarantine and stop sale.",
                                  "source": r["source_url"]})
        if prod:
            if prod["ban_level"]:
                ban = db.one(cur, "SELECT combo_text, notification, notified_on, source_url FROM reg_banned_fdc WHERE id = ?", [prod["ban_id"]])
                if prod["ban_level"] == "exact":
                    flags.append({"level": "critical", "code": "BANNED_FDC",
                                  "message": f"Prohibited FDC: '{ban['combo_text']}' ({ban['notification']}). Remove from shelf.",
                                  "source": ban["source_url"]})
                else:
                    flags.append({"level": "warning", "code": "BAN_REVIEW",
                                  "message": f"Same molecules as prohibited FDC '{ban['combo_text']}' ({ban['notification']}); "
                                             "verify strength/form on the pack.", "source": ban["source_url"]})
            if prod["is_discontinued"]:
                flags.append({"level": "warning", "code": "DISCONTINUED", "message": "Listed as discontinued by the marketer."})
            if prod["company_id"]:
                n = cur.execute("""SELECT count(*) FROM reg_nsq WHERE company_id = ? AND alert_month >= strftime(current_date - INTERVAL 730 DAY, '%Y-%m')""",
                                [prod["company_id"]]).fetchone()[0]
                if n and not any(f["code"].endswith("_BATCH") for f in flags):
                    flags.append({"level": "info", "code": "MAKER_NSQ_HISTORY",
                                  "message": f"{prod['company']} has {n} NSQ/spurious batch listings in the last 24 months."})
            if prod["parent_id"]:
                r = cur.execute("""SELECT count(*) FROM usfda_actions WHERE parent_id = ? AND kind = 'recall' AND issued_on >= current_date - INTERVAL 365 DAY""",
                                [prod["parent_id"]]).fetchone()[0]
                if r:
                    flags.append({"level": "info", "code": "GROUP_USFDA_RECALLS", "message": f"Parent group had {r} USFDA recalls in the last 12 months."})
            # cheaper equivalents
            if prod["combo_id"] and prod["mrp"]:
                cheap = db.one(cur, """SELECT p.id, p.name, p.mrp, p.unit_price, c.name company FROM products p LEFT JOIN companies c ON c.id = p.company_id
                                       WHERE p.combo_id = ? AND coalesce(p.is_discontinued, false) = false AND p.unit_price IS NOT NULL
                                       ORDER BY p.unit_price LIMIT 1""", [prod["combo_id"]])
                if cheap and prod["unit_price"] and cheap["unit_price"] < prod["unit_price"] * 0.7:
                    flags.append({"level": "info", "code": "CHEAPER_BRAND",
                                  "message": f"Same composition: {cheap['name']} ({cheap['company']}) at ₹{cheap['unit_price']:.2f}/unit vs ₹{prod['unit_price']:.2f}.",
                                  "product_id": cheap["id"]})
                mids = [r[0] for r in cur.execute("SELECT molecule_id FROM product_molecules WHERE product_id = ?", [prod["id"]]).fetchall()]
                ja = jan_aushadhi_for(cur, mids, len(mids))
                if ja:
                    flags.append({"level": "info", "code": "JAN_AUSHADHI",
                                  "message": f"Jan Aushadhi generic: {ja[0]['name']} ({ja[0]['unit_size']}) ₹{ja[0]['mrp']}."})
        exp = parse_expiry(it.expiry)
        if exp:
            days = (exp - today).days
            if days < 0:
                flags.append({"level": "critical", "code": "EXPIRED", "message": f"Expired {-days} days ago."})
            elif days <= 90:
                flags.append({"level": "warning", "code": "EXPIRING", "message": f"Expires in {days} days."})
        level = ("critical" if any(f["level"] == "critical" for f in flags) else
                 "warning" if any(f["level"] == "warning" for f in flags) else
                 "info" if flags else "ok")
        if not prod and not flags:
            level = "unmatched"
        counts[level] += 1
        results.append({"input": it.model_dump(), "match": cleanrows([prod])[0] if prod else None, "match_score": score,
                        "level": level, "flags": flags})
    order = {"critical": 0, "warning": 1, "unmatched": 2, "info": 3, "ok": 4}
    results.sort(key=lambda r: order[r["level"]])
    return {"checked_at": datetime.now().isoformat(timespec="seconds"), "counts": counts, "results": results}
