"""CDSCO (Central Drugs Standard Control Organisation) connectors.

* cdsco_nsq      — official monthly NSQ / spurious drug alert PDFs (archive page; official
                   feed stops at Aug 2025 when CDSCO moved NSQ to a new portal).
* nsq_mirror     — The Health Master republishes each monthly CDSCO NSQ/State/Spurious PDF;
                   used for months after the official archive ends. Marked as a mirror.
* cdsco_gazette  — Gazette notifications (FDC prohibitions, rule amendments, schedule changes).
* cdsco_alerts   — Alerts / circulars / public notices (recalls, theft, falsified products).
"""
import io
import re
from datetime import date, datetime

import pdfplumber
from selectolax.lexbor import LexborHTMLParser

from .. import db, matcher
from ..normalize import norm
from .base import Connector

CDSCO = "https://cdsco.gov.in"
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def parse_cdsco_date(s: str) -> date | None:
    for fmt in ("%Y-%b-%d", "%d-%b-%Y", "%d.%m.%Y", "%Y.%m.%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def norm_month(s: str | None) -> str | None:
    """'OCT-2025' / 'Oct 2025' / '2025-10' -> '2025-10'."""
    if not s:
        return None
    t = s.strip().lower()
    if re.match(r"^20\d\d-\d\d$", t):
        return t
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,\-–/]*'?(20\d\d)", t)
    return f"{m.group(2)}-{MONTHS[m.group(1)]:02d}" if m else None


def month_from_title(title: str, fallback: date | None) -> str | None:
    t = title.lower()
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,\-–â\x80\x93]*'?(20\d\d)", t)
    if m:
        return f"{m.group(2)}-{MONTHS[m.group(1)]:02d}"
    if fallback:
        # lists are usually published the month after the sampling month
        y, mo = fallback.year, fallback.month - 1
        if mo == 0:
            y, mo = y - 1, 12
        return f"{y}-{mo:02d}"
    return None


# ------------------------------------------------------------------ NSQ PDF tables
HEADER_MAP = [
    ("product", ("product", "name of drug", "drug name", "name of the drug", "name of product", "name of drugs")),
    ("batch", ("batch",)),
    ("mfg", ("manufactur", "mfg")),   # disambiguated below
    ("exp", ("expiry", "exp.")),
    ("manufacturer", ("manufactured by", "manufacturer", "mfd by", "name of manufacturer")),
    ("reason", ("nsq result", "reason", "result", "test", "parameter")),
    ("lab", ("laboratory", "reported by", "reporting by", "drawn", "lab")),
    ("month", ("reporting month", "month")),
]


def map_header(cells: list[str]) -> dict[int, str] | None:
    low = [norm(c or "") for c in cells]
    if not any("batch" in c for c in low):
        return None
    out = {}
    for i, c in enumerate(low):
        if not c:
            continue
        if "batch" in c:
            out[i] = "batch"
        elif "expir" in c or c.startswith("exp"):
            out[i] = "exp"
        elif ("manufactur" in c and "date" in c) or c in ("mfg date", "mfg dt", "date of manufacture", "manufact uring date"):
            out[i] = "mfg"
        elif "manufactured by" in c or c in ("manufacturer", "name of manufacturer", "mfd by", "manufactured by"):
            out[i] = "manufacturer"
        elif "month" in c:
            out[i] = "month"
        elif any(k in c for k in ("product", "drug", "name of")) and "product" not in out.values():
            out[i] = "product"
        elif any(k in c for k in ("result", "reason", "parameter", "test")):
            out[i] = "reason"
        elif any(k in c for k in ("laborator", "reported", "reporting", "drawn", "lab", "state")):
            out.setdefault(i, "lab")
    if "product" not in out.values():
        return None
    return out


def parse_nsq_pdf(content: bytes) -> list[dict]:
    rows, header = [], None
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for raw in table:
                    cells = [(c or "").replace("\n", " ").strip() for c in raw]
                    h = map_header(cells)
                    if h:
                        header = h
                        continue
                    if not header or len(cells) < max(header) + 1:
                        continue
                    rec = {v: cells[k] for k, v in header.items()}
                    if not rec.get("product") or not rec.get("batch"):
                        continue
                    if norm(rec["product"]) in ("product drug name", "name of product"):
                        continue
                    rows.append(rec)
    return rows


class _NsqBase(Connector):
    agency = "CDSCO"

    def ingest_pdf(self, content: bytes, *, title: str, published: date | None, url: str, mirror: bool):
        category = "SPURIOUS" if "spurious" in title.lower() else "NSQ"
        month = month_from_title(title, published)
        recs = parse_nsq_pdf(content)
        self.stats.rows_seen += len(recs)
        new = 0
        with db.writer() as cur:
            for r in recs:
                key = norm(f"{category}|{r.get('product')}|{r.get('batch')}|{r.get('manufacturer', '')[:60]}")
                if cur.execute("SELECT 1 FROM reg_nsq WHERE dedupe_key = ?", [key]).fetchone():
                    continue
                cid = matcher.company_for(r.get("manufacturer"))
                mids = matcher.molecules_in(r.get("product", ""))
                cur.execute(
                    """INSERT INTO reg_nsq (alert_month, category, product_text, batch_no, mfg_date, exp_date, manufacturer,
                       reason, drawn_by, lab, source_url, company_id, molecule_ids, dedupe_key, fetched_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, now())""",
                    [norm_month(r.get("month")) or month, category, r.get("product"), r.get("batch"), r.get("mfg"), r.get("exp"),
                     r.get("manufacturer"), r.get("reason"), None, r.get("lab"), url, cid,
                     ",".join(map(str, mids)) or None, key],
                )
                new += 1
                parent = None
                if cid:
                    parent = cur.execute("SELECT parent_id FROM companies WHERE id = ?", [cid]).fetchone()[0]
                if category == "SPURIOUS" or parent:
                    self.emit(
                        cur, kind="spurious" if category == "SPURIOUS" else "nsq",
                        severity="critical" if category == "SPURIOUS" else "high",
                        ts=published, title=f"{'SPURIOUS' if category == 'SPURIOUS' else 'NSQ'}: {r.get('product')} batch {r.get('batch')}",
                        body=f"{r.get('manufacturer') or ''} — {r.get('reason') or ''}".strip(" —"),
                        url=url, entity_type="company" if cid else None, entity_id=cid,
                        dedupe_key=f"nsqrow|{key}", payload={"month": month, "mirror": mirror},
                    )
            if recs:
                self.emit(
                    cur, kind="spurious" if category == "SPURIOUS" else "nsq",
                    severity="high", ts=published,
                    title=f"CDSCO {title.strip()[:150]} — {len(recs)} batches" + (" (via mirror)" if mirror else ""),
                    url=url, dedupe_key=f"nsqdoc|{url}", payload={"rows": len(recs), "month": month},
                )
            cur.execute(
                "INSERT OR IGNORE INTO reg_documents (agency, doc_type, title, published_on, url, dedupe_key, fetched_at) VALUES (?,?,?,?,?,?, now())",
                ["CDSCO", "nsq_list", title.strip(), published, url, f"doc|{url}"],
            )
        self.stats.rows_new += new
        return len(recs), new


def cdsco_pdf(conn: Connector, download_url: str) -> bytes | None:
    """CDSCO download links return an HTML wrapper with an <iframe src='...pdf'>."""
    r = conn.get(download_url)
    if r.headers.get("content-type", "").startswith("application/pdf"):
        return r.content
    m = re.search(r"src='([^']+\.pdf)'", r.text, re.I) or re.search(r'src="([^"]+\.pdf)"', r.text, re.I)
    if not m:
        return None
    pdf = conn.get(CDSCO + m.group(1).replace(" ", "%20"))
    if pdf.status_code != 200 or not pdf.content.startswith(b"%PDF"):
        return None
    return pdf.content


def cdsco_listing(conn: Connector, path: str) -> list[dict]:
    """Rows of a standard CDSCO listing page: title, date, download url."""
    html = conn.get(CDSCO + path).text
    out = []
    t = LexborHTMLParser(html)
    for tr in t.css("table tr"):
        tds = tr.css("td")
        a = tr.css_first("a[href*=download_file]")
        if len(tds) >= 3 and a:
            out.append({"title": tds[1].text(strip=True), "date": parse_cdsco_date(tds[2].text(strip=True)),
                        "url": CDSCO + a.attributes["href"]})
    # list-style pages (nsq-drugs)
    for m in re.finditer(r"href='([^']*num_id=[^']*)'>\s*<span[^>]*>\s*([^<]+)</span>.*?</i>\s*(\d{4}-[A-Za-z]{3}-\d{2})", html, re.S):
        out.append({"title": m.group(2).strip(), "date": parse_cdsco_date(m.group(3)), "url": CDSCO + m.group(1)})
    return out


NSQ_TITLE = re.compile(r"nsq|not of standard|standard quality|drug alert|spurious|alert list", re.I)


class CdscoNsq(_NsqBase):
    name = "cdsco_nsq"
    title = "CDSCO NSQ & Spurious Drug Alerts"
    schedule = {"trigger": "cron", "hour": 9, "minute": 10}
    description = "Monthly Not-of-Standard-Quality and spurious drug batch lists (official CDSCO archive)."
    backfill_from = date(2022, 1, 1)

    def run(self):
        items = cdsco_listing(self, "/opencms/opencms/en/Notifications/nsq-drugs/")
        items += [i for i in cdsco_listing(self, "/opencms/opencms/en/Notifications/Alerts/") if NSQ_TITLE.search(i["title"])]
        seen_urls = {r[0] for r in db.cursor().execute("SELECT url FROM reg_documents WHERE agency='CDSCO' AND doc_type='nsq_list'").fetchall()}
        todo = [i for i in items if NSQ_TITLE.search(i["title"]) and i["url"] not in seen_urls
                and (i["date"] or date.today()) >= self.backfill_from]
        todo = list({i["url"]: i for i in todo}.values())
        for it in sorted(todo, key=lambda x: x["date"] or date.min):
            pdf = cdsco_pdf(self, it["url"])
            if not pdf:
                self.stats.notes.append(f"no pdf: {it['title'][:50]}")
                continue
            self.archive(pdf, "pdf")
            n, new = self.ingest_pdf(pdf, title=it["title"], published=it["date"], url=it["url"], mirror=False)
            if n == 0:
                self.stats.notes.append(f"0 rows parsed: {it['title'][:50]}")


class NsqMirror(_NsqBase):
    name = "nsq_mirror"
    title = "CDSCO NSQ lists (Health Master mirror)"
    schedule = {"trigger": "cron", "hour": 9, "minute": 40}
    description = "Monthly CDSCO central/state NSQ and spurious lists republished by thehealthmaster.com, for months after the official archive ends."
    PAGE = "https://thehealthmaster.com/drug-alert-nsq-drugs-lists/"

    def run(self):
        html = self.get(self.PAGE).text
        links = re.findall(r'href="(https://thehealthmaster\.com/wp-content/uploads/[^"]+?\.pdf)"', html)
        cur = db.cursor()
        latest_official = cur.execute(
            "SELECT max(alert_month) FROM reg_nsq WHERE source_url LIKE 'https://cdsco.gov.in%'").fetchone()[0] or "2025-08"
        for url in dict.fromkeys(links):
            fname = url.rsplit("/", 1)[-1]
            if not re.search(r"drug-alert|spurious|nsq", fname, re.I) or re.search(r"2017-2023", fname):
                continue
            title = re.sub(r"[-_]+", " ", fname[:-4])
            month = month_from_title(title, None)
            if not month or month <= latest_official:
                continue
            if cur.execute("SELECT 1 FROM reg_documents WHERE url = ?", [url]).fetchone():
                continue
            r = self.get(url)
            if r.status_code != 200 or not r.content.startswith(b"%PDF"):
                continue
            self.archive(r.content, "pdf")
            y, m = month.split("-")
            pub = date(int(y), int(m), 28)
            if "states" in fname.lower():
                title = "State " + title
            self.ingest_pdf(r.content, title=title, published=pub, url=url, mirror=True)


# ------------------------------------------------------------------ gazette / alerts
BAN_TITLE = re.compile(r"prohibit|banned|ban on|restrict", re.I)


class CdscoGazette(Connector):
    name = "cdsco_gazette"
    title = "CDSCO Gazette Notifications"
    agency = "CDSCO"
    schedule = {"trigger": "cron", "hour": 8, "minute": 50}
    description = "Gazette notifications: FDC prohibitions, Drugs Rules amendments, schedule changes, draft rules."

    def run(self):
        items = cdsco_listing(self, "/opencms/opencms/en/Notifications/Gazette-Notifications/")
        self.stats.rows_seen = len(items)
        with db.writer() as cur:
            for it in items:
                key = f"doc|{it['url']}"
                if cur.execute("SELECT 1 FROM reg_documents WHERE dedupe_key = ?", [key]).fetchone():
                    continue
                t = it["title"]
                kind = "ban" if BAN_TITLE.search(t) else "gazette"
                doc_type = "prohibition" if kind == "ban" else ("draft_rule" if "draft" in t.lower() else "notification")
                cur.execute(
                    "INSERT INTO reg_documents (agency, doc_type, title, published_on, url, dedupe_key, fetched_at) VALUES (?,?,?,?,?,?, now())",
                    ["CDSCO", doc_type, t, it["date"], it["url"], key],
                )
                self.stats.rows_new += 1
                mids = matcher.molecules_in(t)
                recent = it["date"] and (date.today() - it["date"]).days <= 400
                if recent or kind == "ban":
                    self.emit(cur, kind=kind, severity="critical" if kind == "ban" else "medium", ts=it["date"],
                              title=f"Gazette: {t[:220]}", url=it["url"],
                              entity_type="molecule" if len(mids) == 1 else None,
                              entity_id=mids[0] if len(mids) == 1 else None,
                              dedupe_key=key, payload={"molecule_ids": mids})


ALERT_KIND = [
    (re.compile(r"recall", re.I), "recall", "high"),
    (re.compile(r"spurious|falsif|counterfeit|fake|theft", re.I), "spurious", "critical"),
    (re.compile(r"nsq|standard quality|drug alert", re.I), "nsq", "high"),
    (re.compile(r"approv|permission", re.I), "approval", "medium"),
]


class CdscoAlerts(Connector):
    name = "cdsco_alerts"
    title = "CDSCO Alerts, Circulars & Public Notices"
    agency = "CDSCO"
    schedule = {"trigger": "cron", "hour": "8,14,20", "minute": 5}
    description = "Safety alerts, recalls, falsified-product warnings, circulars and public notices."

    PAGES = [
        ("/opencms/opencms/en/Notifications/Alerts/", "alert"),
        ("/opencms/opencms/en/Notifications/Circulars/", "circular"),
        ("/opencms/opencms/en/Notifications/Public-Notices/", "public_notice"),
    ]

    def run(self):
        for path, doc_type in self.PAGES:
            try:
                items = cdsco_listing(self, path)
            except Exception as e:  # noqa: BLE001
                self.stats.notes.append(f"{doc_type}: {e}")
                continue
            self.stats.rows_seen += len(items)
            with db.writer() as cur:
                for it in items:
                    key = f"doc|{it['url']}"
                    if cur.execute("SELECT 1 FROM reg_documents WHERE dedupe_key = ?", [key]).fetchone():
                        continue
                    cur.execute(
                        "INSERT INTO reg_documents (agency, doc_type, title, published_on, url, dedupe_key, fetched_at) VALUES (?,?,?,?,?,?, now())",
                        ["CDSCO", doc_type, it["title"], it["date"], it["url"], key],
                    )
                    self.stats.rows_new += 1
                    if not it["date"] or (date.today() - it["date"]).days > 400:
                        continue
                    kind, sev = "gazette", "info"
                    for rx, k, s in ALERT_KIND:
                        if rx.search(it["title"]):
                            kind, sev = k, s
                            break
                    pid = matcher.parent_for(it["title"]) or (matcher.parents_in(it["title"]) or [None])[0]
                    self.emit(cur, kind=kind, severity=sev, ts=it["date"], title=f"CDSCO: {it['title'][:220]}",
                              url=it["url"], entity_type="parent" if pid else None, entity_id=pid, dedupe_key=key)


# ------------------------------------------------------------------ banned / restricted FDCs
FDC_DOC = re.compile(r"(prohibit|banned|restricted).*(fdc|drug)|section 26a", re.I)
FORM_NOISE = re.compile(
    r"\b(ip|bp|usp|tablets?|capsules?|syrup|suspension|injection|dispersible|hard gelatin|or|and|oral|drops?|"
    r"cream|gel|ointment|lotion|liquid|powder|solution|sachets?|granules|\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|%)[^\s+]*)\b",
    re.I,
)
STATUS_STAYED = re.compile(r"stay|stayed|quash|set aside|revok|withdrawn|rescind|omitted", re.I)


def fdc_mkey(text: str) -> tuple[str | None, list[str]]:
    """'Amoxicillin + Bromhexine' -> ('amoxicillin|bromhexine', [...]). None for class-level bans."""
    from ..normalize import molecule_key
    if "+" not in text:
        return None, []
    parts = []
    for p in text.split("+"):
        p = FORM_NOISE.sub(" ", p)
        p = re.sub(r"\(.*?\)", " ", p)
        k = molecule_key(p)
        if not k or len(k) < 3 or len(k.split()) > 4:
            return None, []
        parts.append(k)
    parts = sorted(set(parts))
    return ("|".join(parts) if len(parts) >= 2 else None), parts


def parse_fdc_pdf(content: bytes) -> list[dict]:
    # long entries wrap across several table rows; continuation rows have an empty S.No cell
    recs: list[dict] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for raw in table:
                    cells = [(c or "").replace("\n", " ").strip() for c in raw]
                    if len(cells) < 3:
                        continue
                    if re.match(r"^\d+\.?$", cells[0]):
                        recs.append({"name": [cells[1]], "notif": [" ".join(cells[2:])]})
                    elif not cells[0] and recs and (cells[1] or any(cells[2:])):
                        recs[-1]["name"].append(cells[1])
                        recs[-1]["notif"].append(" ".join(cells[2:]))
    out = []
    for r in recs:
        name = re.sub(r"\s+", " ", " ".join(x for x in r["name"] if x)).strip()
        notif = re.sub(r"\s+", " ", " ".join(x for x in r["notif"] if x)).strip()
        compact = re.sub(r"\s+", "", notif)
        d = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", compact)
        when = None
        if d:
            try:
                when = date(int(d.group(3)), int(d.group(2)), int(d.group(1)))
            except ValueError:
                when = None
        out.append({"name": name, "notification": re.sub(r"\s*dated.*$", "", notif, flags=re.I).strip(),
                    "date": when, "row": f"{name} {notif}"})
    return out


class CdscoBannedFdc(Connector):
    name = "banned_fdc"
    title = "CDSCO Prohibited & Restricted FDCs"
    agency = "CDSCO / MoHFW"
    schedule = {"trigger": "cron", "hour": 9, "minute": 0}
    description = "Drugs and fixed-dose combinations prohibited under Section 26A of the Drugs & Cosmetics Act (all notifications since 1983)."

    def run(self):
        items = [i for i in cdsco_listing(self, "/opencms/opencms/en/Drugs/FDC/") if FDC_DOC.search(i["title"])]
        # oldest first so later notifications (incl. stays) win
        for it in sorted(items, key=lambda x: x["date"] or date.min):
            with db.cursor() as c0:
                if c0.execute("SELECT 1 FROM reg_documents WHERE url = ? AND doc_type = 'fdc_list'", [it["url"]]).fetchone():
                    continue
            pdf = cdsco_pdf(self, it["url"])
            if not pdf:
                self.stats.notes.append(f"no pdf: {it['title'][:40]}")
                continue
            self.archive(pdf, "pdf")
            rows = parse_fdc_pdf(pdf)
            self.stats.rows_seen += len(rows)
            restricted = "restrict" in it["title"].lower()
            with db.writer() as cur:
                for r in rows:
                    mkey, parts = fdc_mkey(r["name"])
                    status = "restricted" if restricted else ("stayed" if STATUS_STAYED.search(r["row"]) else "banned")
                    key = norm(f"{r['name']}|{r['notification']}")
                    exists = cur.execute("SELECT status FROM reg_banned_fdc WHERE dedupe_key = ?", [key]).fetchone()
                    if exists:
                        if exists[0] != status:
                            cur.execute("UPDATE reg_banned_fdc SET status = ? WHERE dedupe_key = ?", [status, key])
                        continue
                    cur.execute(
                        """INSERT INTO reg_banned_fdc (combo_text, mkey, notification, notified_on, status, source_url, dedupe_key, fetched_at)
                           VALUES (?,?,?,?,?,?,?, now())""",
                        [r["name"], mkey, r["notification"], r["date"], status, it["url"], key],
                    )
                    self.stats.rows_new += 1
                    if r["date"] and (date.today() - r["date"]).days <= 400 and status != "stayed":
                        live = 0
                        if mkey:
                            live = cur.execute(
                                "SELECT coalesce(sum(product_count),0) FROM combos WHERE mkey = ?", [mkey]).fetchone()[0]
                        self.emit(cur, kind="ban", severity="critical", ts=r["date"],
                                  title=f"{'RESTRICTED' if restricted else 'BANNED'} FDC: {r['name'][:180]}"
                                        + (f" — {live} catalog SKUs affected" if live else ""),
                                  body=r["notification"], url=it["url"], dedupe_key=f"ban|{key}",
                                  payload={"mkey": mkey, "skus": live})
                cur.execute(
                    "INSERT OR IGNORE INTO reg_documents (agency, doc_type, title, published_on, url, dedupe_key, fetched_at) VALUES (?,?,?,?,?,?, now())",
                    ["CDSCO", "fdc_list", it["title"], it["date"], it["url"], f"fdclist|{it['url']}"],
                )
