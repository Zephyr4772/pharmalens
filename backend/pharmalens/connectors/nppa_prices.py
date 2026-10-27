"""NPPA retail-price notifications: the official per-unit price NPPA fixes for each new drug before launch.

Every Gazette order (S.O.) lists formulation, strength, unit, manufacturer / marketing company and the retail
price per unit excluding GST. The PDFs are bilingual (Hindi pages first, English after); only the English table is
read. Current notices come from the NPPA "What's new" list, older ones (2019 onwards) from its archive. Each PDF is
parsed once and remembered in connector_state.
"""
import io
import re
from datetime import date, datetime

import pdfplumber
from selectolax.lexbor import LexborHTMLParser

from .. import db, matcher
from .base import Connector
from .gov_india import NPPA, nppa_date

LISTINGS = ["view_more?id=4", "archieve?id=4&arc=1"]
FINAL = re.compile(r"retail price|fixed retail|retail prices", re.I)
NOT_FINAL = re.compile(r"draft|worksheet|calculation sheet|ceiling|faq|clarification|form[- ]?ia|extension|hiring", re.I)
COLUMNS = [("sl", r"^s\.?\s*no|^sl"), ("price", r"price"), ("unit", r"^unit"), ("strength", r"strength|composition"),
           ("company", r"manufactur|company|marketing"), ("formulation", r"formulation|brand|medicine|name")]


def kind_of(title: str) -> str:
    t = title.lower()
    if "without prior" in t:
        return "without_prior_approval"
    if "revis" in t or "review" in t:
        return "revision"
    return "new_drug"


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip()


def _header_map(row: list) -> dict | None:
    cells = [_clean(c).lower() for c in row]
    if not any("price" in c for c in cells):
        return None
    m = {}
    for i, c in enumerate(cells):
        for col, pat in COLUMNS:
            if col not in m and re.search(pat, c):
                m[col] = i
                break
    return m if {"formulation", "price"} <= m.keys() else None


def company_pairs(text: str) -> list[tuple[str, str]]:
    """'(i) M/s A Ltd./ M/s B Ltd.; (ii) M/s A Ltd./ M/s C Ltd.' -> [(A, B), (A, C)]: manufacturer, marketer."""
    text = re.sub(r"\bM\s*/\s*[sS]\.?\s*|\bMs\.?\s+(?=[A-Z])", "", _clean(text))
    out = []
    for part in re.split(r"\(\s*[ivx]+\s*\)|;", text):
        part = part.strip(" ,;")
        if not part:
            continue
        bits = [b.strip(" ,.") for b in re.split(r"\s*/\s*", part) if b.strip(" ,.")]
        if not bits:
            continue
        out.append((bits[0], bits[-1]))
    return out


def parse_pdf(content: bytes) -> tuple[str | None, list[dict]]:
    """English table rows of one notification: (S.O. number, rows)."""
    rows, header, so = [], None, None
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            if not so:
                m = re.search(r"S\.\s*O\.\s*(\d+)\s*\(\s*E\s*\)", page.extract_text() or "")
                so = f"{m.group(1)}(E)" if m else None
            for table in page.extract_tables():
                # language per table, not per page: one page can end the Hindi notes and start the English table
                cells = "".join(c or "" for r in table for c in r)
                if not cells or sum(c.isascii() for c in cells) / len(cells) < 0.9:
                    continue
                for raw in table:
                    h = _header_map(raw)
                    if h:
                        header = h
                        continue
                    if not header or len(raw) <= max(header.values()):
                        continue
                    cell = {k: _clean(raw[i]) for k, i in header.items()}
                    if re.fullmatch(r"\(\d+\)", cell.get("sl", "") or cell.get("formulation", "")):
                        continue   # the (1) (2) (3) column-number row
                    if re.fullmatch(r"\d+\.?", cell.get("sl", "")):
                        rows.append(cell)
                    elif rows and any(cell.values()):
                        # a row split across lines or pages: glue the fragment onto the record it belongs to
                        for k, v in cell.items():
                            if v:
                                rows[-1][k] = f"{rows[-1].get(k, '')} {v}".strip()
    out = []
    for r in rows:
        nums = re.findall(r"\d+(?:\.\d+)?", r.get("price", "").replace(",", ""))
        if not nums:
            continue
        r["price"] = float(nums[-1])
        r["sl"] = r.get("sl", "").rstrip(".")
        out.append(r)
    return so, out


class NppaRetailPrices(Connector):
    name = "nppa_retail_prices"
    title = "NPPA Retail Price Notifications (new drugs)"
    agency = "NPPA"
    schedule = {"trigger": "cron", "hour": "10,17", "minute": 45}
    description = ("Official per-unit retail price NPPA fixes for every new drug (Gazette S.O.), with manufacturer and "
                   "marketer, from 2019 onwards: launch prices straight from the regulator.")
    per_run = 40   # PDFs parsed per run; the archive backfills over a few runs

    def _listing(self, path: str) -> list[dict]:
        out = []
        for tr in LexborHTMLParser(self.get(NPPA + path).text).css("table tr"):
            a = tr.css_first("a[href$='.pdf']")
            if not a:
                continue
            text = _clean(tr.text())
            m = re.search(r"\d{1,2}[-./][A-Za-z]{3}[-./]\d{4}|\d{2}[./]\d{2}[./]\d{4}", text)
            out.append({"date": nppa_date(m.group(0)) if m else None, "title": text, "url": a.attributes.get("href")})
        return out

    def run(self):
        docs, seen_urls = [], set()
        for path in LISTINGS:
            try:
                for d in self._listing(path):
                    if d["url"] in seen_urls or not FINAL.search(d["title"]) or NOT_FINAL.search(d["title"]):
                        continue
                    seen_urls.add(d["url"])
                    docs.append(d)
            except Exception as e:  # noqa: BLE001
                self.stats.notes.append(f"{path}: {e}")
        cur = db.cursor()
        done = {r[0] for r in cur.execute("SELECT key FROM connector_state WHERE key LIKE 'nppaprice|%'").fetchall()}
        todo = sorted((d for d in docs if f"nppaprice|{d['url']}" not in done),
                      key=lambda d: d["date"] or date.min, reverse=True)[: self.per_run]
        self.stats.notes.append(f"{len(docs)} notifications listed, {len(todo)} to parse")
        for d in todo:
            try:
                r = self.get(d["url"])
                so, rows = parse_pdf(r.content) if r.status_code == 200 else (None, [])
            except Exception as e:  # noqa: BLE001 — one bad PDF must not stop the backfill
                self.stats.notes.append(f"{d['url'].rsplit('/', 1)[-1]}: {str(e)[:80]}")
                continue
            self.stats.rows_seen += len(rows)
            fresh = d["date"] and (date.today() - d["date"]).days <= 120
            marketers = []
            with db.writer() as w:
                for r in rows:
                    # actives only: "hard gelatin capsule" must not add Gelatin
                    mids = sorted(set(matcher.actives_in(r.get("formulation") or "")
                                      or matcher.actives_in(r.get("strength") or "")))
                    for i, (maker, marketer) in enumerate(company_pairs(r.get("company", "")) or [(None, None)]):
                        key = f"{d['url']}|{r['sl']}|{i}"
                        if w.execute("SELECT 1 FROM nppa_retail_prices WHERE key = ?", [key]).fetchone():
                            continue
                        company_id = matcher.company_for(marketer) if marketer else None
                        w.execute("""INSERT INTO nppa_retail_prices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, now())""",
                                  [key, d["date"], so, kind_of(d["title"]), d["title"][:300], d["url"], r["sl"],
                                   r.get("formulation"), r.get("strength"), r.get("unit"), maker, marketer, company_id,
                                   r["price"], ",".join(map(str, mids)) or None])
                        self.stats.rows_new += 1
                        if marketer and marketer not in marketers:
                            marketers.append(marketer)
                if fresh and rows:
                    # one event per notification, not per formulation: a Gazette order can carry dozens
                    who = ", ".join(marketers[:4]) + (f" +{len(marketers) - 4} more" if len(marketers) > 4 else "")
                    first = rows[0]
                    self.emit(w, kind="launch", severity="info", ts=d["date"],
                              title=f"NPPA fixed prices for {len(rows)} new formulation{'s' * (len(rows) > 1)}"
                                    f"{f' ({who})' if who else ''}",
                              body=f"e.g. {first.get('formulation')}: ₹{first['price']:g} per {first.get('unit') or 'unit'}",
                              url=d["url"], dedupe_key=f"nppaprice|{d['url']}")
                w.execute("INSERT OR REPLACE INTO connector_state VALUES (?, ?)",
                          [f"nppaprice|{d['url']}", f"{datetime.now().isoformat()}|{len(rows)}"])
        total = cur.execute("SELECT count(*) FROM nppa_retail_prices").fetchone()[0]
        self.stats.notes.append(f"{total:,} notified prices stored")
