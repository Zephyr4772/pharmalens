"""Public procurement prices and global safety alerts.

* rmscl_rates    — Rajasthan Medical Services Corporation active rate contracts: what the state actually
                   pays per unit, by supplier and L1/L2 rank, with contract validity. Free-medicine scheme.
* who_alerts     — WHO Medical Product Alerts (falsified / substandard products worldwide).
* fda_ia_6640    — US FDA Import Alert 66-40: firms whose drugs are detained for cGMP failures (red list).
"""
import re
from datetime import date, datetime

from selectolax.lexbor import LexborHTMLParser

from .. import db, matcher
from ..normalize import fix_mojibake, norm
from .base import Connector


def dmy(s: str | None) -> date | None:
    for fmt in ("%d-%b-%Y", "%d %B %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime((s or "").strip().title(), fmt).date()
        except ValueError:
            continue
    return None


RATE_COLS = ("buyer, state, item_code, item, kind, tender_no, supplier, company_id, unit, rate, gst, level, valid_from, valid_to, "
             "molecule_ids, source_url, fetched_at, category, order_share")
SURGICAL = re.compile(r"(?i)gauze|catheter|syringe|glove|bandage|cannula|needle|tube|blade|dressing|mask|bag|drape|plaster|cotton")


def item_kind(item: str, category: str = "") -> str:
    c = category.lower()
    if "suture" in c or "SUTURE" in item.upper():
        return "suture"
    if "surgical" in c or SURGICAL.search(item):
        return "surgical"
    return "veterinary" if "veterinary" in c else "drug"


class RmsclRates(Connector):
    name = "rmscl_rates"
    title = "Rajasthan RMSCL Drug Rate Contracts"
    agency = "RMSCL (Govt of Rajasthan)"
    schedule = {"trigger": "cron", "day_of_week": "tue,fri", "hour": 12, "minute": 30}
    description = "Government procurement price per unit for drugs, surgicals and sutures, by supplier and L-rank, with contract dates."
    URL = "https://rmsc.health.rajasthan.gov.in/content/raj/medical/rajasthan-medical-services-corporation-ltd-/en/Approved-Rate-Lists/DrugsRC.html"

    def run(self):
        html = self.get(self.URL).text
        self.archive(html, "html", key=f"rmscl-{date.today():%Y%m%d}")
        rows = []
        for tr in LexborHTMLParser(html).css("table tr"):
            c = [td.text(strip=True) for td in tr.css("td")]
            if len(c) < 11 or not c[0]:
                continue
            try:
                rate = float(c[6].replace(",", ""))
            except ValueError:
                rate = None
            rows.append({"item": fix_mojibake(c[0]), "code": c[1], "tender": c[2], "supplier": c[3], "unit": c[5], "rate": rate,
                         "gst": c[7], "level": c[8], "from": dmy(c[9]), "to": dmy(c[10])})
        self.stats.rows_seen = len(rows)
        if len(rows) < 200:
            raise RuntimeError(f"RMSCL table parse looks wrong ({len(rows)} rows)")
        with db.writer() as w:
            prev = {(r[0], r[1], r[2]): r[3] for r in w.execute("SELECT item_code, supplier, level, rate FROM procurement_rates WHERE buyer = 'RMSCL'").fetchall()}
            w.execute("DELETE FROM procurement_rates WHERE buyer = 'RMSCL'")
            for r in rows:
                kind = item_kind(r["item"])
                mids = matcher.molecules_in(r["item"], limit=5) if kind == "drug" else []
                w.execute(f"INSERT INTO procurement_rates ({RATE_COLS}) VALUES ('RMSCL', 'Rajasthan', ?,?,?,?,?,?,?,?,?,?,?,?,?,?, now(), 'drug', NULL)",
                          [r["code"], r["item"], kind, r["tender"], r["supplier"], matcher.company_for(r["supplier"]), r["unit"], r["rate"],
                           r["gst"], r["level"], r["from"], r["to"], ",".join(map(str, mids)) or None, self.URL])
                old = prev.get((r["code"], r["supplier"], r["level"]))
                if prev and old is None and r["level"] == "L1":
                    self.stats.rows_new += 1
            if not prev:
                self.stats.rows_new = len(rows)


class WhoAlerts(Connector):
    name = "who_alerts"
    title = "WHO Medical Product Alerts"
    agency = "WHO"
    schedule = {"trigger": "cron", "hour": 8, "minute": 15}
    description = "WHO alerts on falsified and substandard medical products circulating worldwide."
    URL = "https://www.who.int/teams/regulation-prequalification/incidents-and-SF/full-list-of-who-medical-product-alerts"

    def run(self):
        html = self.get(self.URL).text
        self.archive(html, "html", key=f"who-alerts-{date.today():%Y%m%d}")
        seen = {}
        for a in LexborHTMLParser(html).css("a"):
            href = a.attributes.get("href") or ""
            if "medical-product-alert" not in href:
                continue
            url = href if href.startswith("http") else "https://www.who.int" + href
            txt = re.sub(r"\s+", " ", a.text(strip=True))
            m = re.match(r"(\d{1,2} \w+ \d{4})\s*Medical product alert\s*(.*)", txt, re.I)
            seen[url] = (dmy(m.group(1)) if m else None, (m.group(2) if m else txt)[:400])
        self.stats.rows_seen = len(seen)
        with db.writer() as w:
            for url, (when, title) in seen.items():
                key = f"doc|{url}"
                if w.execute("SELECT 1 FROM reg_documents WHERE dedupe_key = ?", [key]).fetchone():
                    continue
                w.execute("INSERT INTO reg_documents (agency, doc_type, title, published_on, url, dedupe_key, fetched_at) VALUES ('WHO','product_alert',?,?,?,?, now())",
                          [title, when, url, key])
                self.stats.rows_new += 1
                mids = matcher.molecules_in(title, limit=4)
                if when and (date.today() - when).days <= 365:
                    self.emit(w, kind="spurious" if "falsified" in title.lower() else "recall", severity="high", ts=when,
                              title=f"WHO alert: {title[:200]}", url=url, entity_type="molecule" if len(mids) == 1 else None,
                              entity_id=mids[0] if len(mids) == 1 else None, dedupe_key=key, payload={"molecule_ids": mids})


class FdaImportAlert6640(Connector):
    name = "fda_ia_6640"
    title = "US FDA Import Alert 66-40 (cGMP)"
    agency = "US FDA"
    schedule = {"trigger": "cron", "day_of_week": "mon", "hour": 7, "minute": 40}
    description = "Firms on FDA's red list for drugs not made under cGMP; Indian sites flagged and linked to groups."
    URL = "https://www.accessdata.fda.gov/cms_ia/importalert_189.html"

    def run(self):
        html = self.get(self.URL, timeout=120).text
        self.archive(html, "html", key=f"ia6640-{date.today():%Y%m%d}")
        # page layout: <h4>COUNTRY</h4> then one div.div-info per firm (name, "Date Published : mm/dd/yyyy", address)
        firms, seen, country = [], set(), None
        for node in LexborHTMLParser(html).css("h4, div.div-info"):
            if node.tag == "h4":
                country = node.text(strip=True).title()
                continue
            parts = node.css("div.div-name")
            name = re.sub(r"\s+", " ", parts[0].text(strip=True)) if parts else ""
            pub = re.search(r"(\d{2}/\d{2}/\d{4})", parts[1].text()) if len(parts) > 1 else None
            a = node.css_first("div.clear")
            addr = re.sub(r"\s+", " ", a.text(strip=True)).replace(" ,", ",") if a else ""
            if not name or (name, addr) in seen:
                continue
            seen.add((name, addr))
            firms.append({"firm": name, "country": country, "address": addr[:300],
                          "published": datetime.strptime(pub.group(1), "%m/%d/%Y").date() if pub else None})
        self.stats.rows_seen = len(firms)
        with db.writer() as w:
            known = {r[0] for r in w.execute("SELECT id FROM usfda_actions WHERE kind = 'import_alert'").fetchall()}
            for f in firms:
                fid = "ia6640-" + norm(f["firm"] + " " + f["address"])[:120]
                if fid in known:
                    continue
                pid = matcher.parent_for(f["firm"], region="global")
                w.execute("INSERT OR REPLACE INTO usfda_actions VALUES (?,?,?,?,?,?,?,?, now())",
                          [fid, "import_alert", f["firm"], f["country"], f"Import Alert 66-40 (cGMP) — {f['address']}", f["published"], self.URL, pid])
                self.stats.rows_new += 1
                if known and f["country"] == "India":
                    self.emit(w, kind="usfda", severity="critical" if pid else "high", ts=f["published"],
                              title=f"USFDA Import Alert 66-40: {f['firm']}", url=self.URL,
                              entity_type="parent" if pid else None, entity_id=pid, dedupe_key=f"ia|{fid}")


class TnmscRates(Connector):
    name = "tnmsc_rates"
    title = "Tamil Nadu TNMSC Tender Rates"
    agency = "TNMSC (Govt of Tamil Nadu)"
    schedule = {"trigger": "cron", "day_of_week": "wed,sat", "hour": 12, "minute": 50}
    description = "L1 rate per pack for every tendered drug, surgical, suture and veterinary item, with each matched supplier and its order share."
    HOME = "https://www.tnmsc.tn.gov.in/"
    PAGE = "https://tnmsc.tn.gov.in/user_pages/drugtender.php?drugcat="
    # tender pages the homepage has linked at some point (it rotates which ones it shows); older ones keep rate history
    KNOWN = {"edl2024": "Essential Drug", "edl2023": "Essential Drug", "T21083": "Essential Drug", "T19062": "Essential Drug",
             "t25048": "Speciality Drug", "t23017": "Speciality Drug", "t22005": "Speciality Drug",
             "t25031": "Veterinary Drug", "t23018": "Veterinary Drug", "t20076": "Veterinary Drug",
             "t24010": "Surgical", "t22057": "Surgical", "t20075": "Surgical", "t18033": "Surgical",
             "t25001": "Suture", "t22027": "Suture", "t18036": "Suture"}

    def run(self):
        home = self.get(self.HOME).text
        cats = dict(self.KNOWN)
        for a in LexborHTMLParser(home).css("a"):
            m = re.search(r"drugtender\.php\?drugcat=(\w+)", a.attributes.get("href") or "")
            if not m or m.group(1).lower().startswith("qct"):
                continue
            label = a.text(strip=True)
            label = TAMIL.get(label, label)
            if label.isascii() or m.group(1) not in cats:
                cats[m.group(1)] = label
        rows = []
        for cat, label in cats.items():
            html = self.get(self.PAGE + cat, timeout=120).text
            self.archive(html, "html", key=f"tnmsc-{cat}-{date.today():%Y%m%d}")
            table = LexborHTMLParser(html).css_first("table")
            if table is None:
                continue
            for tr in table.css("tr"):
                tds = tr.css("td")
                if len(tds) < 11 or not tds[0].text(strip=True).isdigit():
                    continue
                c = [td.text(strip=True) for td in tds[:10]]
                if not c[1] or not c[2]:
                    continue
                sup = tds[10].css_first("table")
                lines = []
                for s in (sup.css("tr") if sup else []):
                    sc = [x.text(strip=True) for x in s.css("td")]
                    if len(sc) >= 6 and sc[0].isdigit():
                        lines.append(sc)
                for sc in lines or [[None, None, None, "Y", c[4], None]]:
                    rows.append({"code": c[1], "item": fix_mojibake(c[2]), "unit": c[3], "tender": c[8], "category": label, "cat": cat,
                                 "supplier": re.sub(r"\s*\(U\d+\)$", "", sc[1] or "") or None, "gst": sc[2],
                                 "level": "L1" if sc[3] == "Y" else ("matched" if sc[3] == "M" else (sc[3] or ("not_finalised" if "NOT FINAL" in c[9].upper() else None))),
                                 "rate": num(sc[4]) if sc[4] else num(c[4]), "share": num(sc[5])})
        self.stats.rows_seen = len(rows)
        if len(rows) < 500:
            raise RuntimeError(f"TNMSC parse looks wrong ({len(rows)} rows from {len(cats)} pages)")
        mol_cache: dict[str, list[int]] = {}
        with db.writer() as w:
            before = w.execute("SELECT count(*) FROM procurement_rates WHERE buyer = 'TNMSC'").fetchone()[0]
            w.execute("DELETE FROM procurement_rates WHERE buyer = 'TNMSC'")
            for r in rows:
                kind = item_kind(r["item"], r["category"])
                if kind in ("drug", "veterinary") and r["item"] not in mol_cache:
                    mol_cache[r["item"]] = matcher.molecules_in(r["item"], limit=5)
                mids = mol_cache.get(r["item"]) or []
                w.execute(f"INSERT INTO procurement_rates ({RATE_COLS}) VALUES ('TNMSC','Tamil Nadu',?,?,?,?,?,?,?,?,?,?,NULL,NULL,?,?, now(),?,?)",
                          [r["code"], r["item"], kind, r["tender"], r["supplier"], matcher.company_for(r["supplier"]), r["unit"], r["rate"],
                           r["gst"], r["level"], ",".join(map(str, mids)) or None, self.PAGE + r["cat"], r["category"], r["share"]])
            self.stats.rows_new = max(0, len(rows) - before)
        self.stats.notes.append(f"{len(cats)} tender pages · {len({r['code'] + r['cat'] for r in rows}):,} items · {len(rows):,} supplier rates")


def num(s: str | None) -> float | None:
    try:
        return float((s or "").replace(",", ""))
    except ValueError:
        return None


TAMIL = {"அத்தியாவசிய மருந்து": "Essential Drug", "அறுவைசிகிச்சை": "Surgical", "சிறப்பு மருந்து": "Speciality Drug",
         "கால்நடை மருந்து": "Veterinary Drug", "தையல் பொருள்": "Suture"}


class HmsclRates(Connector):
    name = "hmscl_rates"
    title = "Haryana HMSCL Rate Contracts"
    agency = "HMSCL (Govt of Haryana)"
    schedule = {"trigger": "cron", "day_of_week": "thu", "hour": 13, "minute": 10}
    description = "Rate per unit (excl. GST) for every drug, surgical and suture on the Haryana essential list, with vendor and validity."
    URL = "https://hmscl.org.in/Page.aspx?slug=drugs-surgical-sutures&q=&group=&level=&pageSize=25&page={}"

    def run(self):
        rows, page, pages = [], 1, 1
        while page <= pages and page <= 60:
            html = self.get(self.URL.format(page), timeout=60).text
            self.archive(html, "html", key=f"hmscl-{date.today():%Y%m%d}-p{page}")
            m = re.search(r"Page \d+ of (\d+)", html)
            pages = int(m.group(1)) if m else page
            for tr in LexborHTMLParser(html).css("table tr"):
                c = [td.text(strip=True) for td in tr.css("td")]
                if len(c) < 9 or not c[0].isdigit():
                    continue
                rows.append({"code": c[1], "edl": fix_mojibake(c[2]), "item": fix_mojibake(c[3] or c[2]), "rc": c[4], "rate": num(c[5]),
                             "supplier": c[6], "from": dmy(c[7]), "to": dmy(c[8])})
            page += 1
        self.stats.rows_seen = len(rows)
        if len(rows) < 100:
            raise RuntimeError(f"HMSCL parse looks wrong ({len(rows)} rows from {pages} pages)")
        with db.writer() as w:
            before = w.execute("SELECT count(*) FROM procurement_rates WHERE buyer = 'HMSCL'").fetchone()[0]
            w.execute("DELETE FROM procurement_rates WHERE buyer = 'HMSCL'")
            for r in rows:
                kind = item_kind(r["edl"])
                mids = matcher.molecules_in(r["edl"], limit=5) if kind == "drug" else []
                # rates are per the contract's unit as written in the item ("10*10", "170 ml bottle")
                unit = (re.search(r",\s*([^,]*\d[^,]*)$", r["item"]) or [None, None])[1]
                w.execute(f"INSERT INTO procurement_rates ({RATE_COLS}) VALUES ('HMSCL','Haryana',?,?,?,?,?,?,?,?,NULL,'RC',?,?,?,?, now(),?,NULL)",
                          [r["code"], r["item"], kind, r["rc"], r["supplier"], matcher.company_for(r["supplier"]), unit, r["rate"],
                           r["from"], r["to"], ",".join(map(str, mids)) or None, self.URL.format(1), "Essential Drug List"])
            self.stats.rows_new = max(0, len(rows) - before)
        self.stats.notes.append(f"{pages} pages · {len(rows):,} contracts")


class UpmsclDebarments(Connector):
    name = "upmscl_debarments"
    title = "Uttar Pradesh UPMSCL Firm Blacklisting"
    agency = "UPMSCL (Govt of Uttar Pradesh)"
    schedule = {"trigger": "cron", "hour": 10, "minute": 35}
    description = "Firms blacklisted by UP's medical supplies corporation, mostly for NSQ batches: drug, reason, order, date and duration."
    URL = "https://upmsc.in/Home/NSQ"
    relay_url = URL          # upmsc.in drops connections from cloud IPs

    def run(self):
        html = self.get_or_relay(self.URL, timeout=40)
        self.archive(html, "html", key=f"upmscl-nsq-{date.today():%Y%m%d}")
        rows = []
        for tr in LexborHTMLParser(html).css("table tr"):
            tds = tr.css("td")
            if len(tds) < 8 or not tds[0].text(strip=True).isdigit():
                continue
            c = [re.sub(r"\s+", " ", td.text(strip=True)) for td in tds]
            a = tds[8].css_first("a") if len(tds) > 8 else None
            drug = re.sub(r"(?i)^firm blacklisted for (?:the )?drug\s*-\s*", "", c[1]).strip()
            rows.append({"what": c[1], "drug": drug, "firm": c[2], "address": c[3], "reason": c[4], "order": c[5],
                         "date": dmy(c[6]), "years": num(c[7]),
                         "doc": doc_url(a.attributes.get("href", "")) if a else None})
        self.stats.rows_seen = len(rows)
        if not rows:
            raise RuntimeError("UPMSCL blacklisting table not found")
        with db.writer() as w:
            for r in rows:
                key = norm(f"upmscl|{r['order']}|{r['firm']}|{r['drug'][:60]}")
                if w.execute("SELECT 1 FROM firm_debarments WHERE dedupe_key = ?", [key]).fetchone():
                    continue
                cid = matcher.company_for(r["firm"])
                pid = matcher.parent_for(r["firm"])
                mids = matcher.molecules_in(r["drug"], limit=5)
                w.execute("""INSERT INTO firm_debarments (authority, state, firm, address, subject, drug_text, reason, order_no, ordered_on,
                             years, document_url, company_id, parent_id, molecule_ids, source_url, dedupe_key, fetched_at)
                             VALUES ('UPMSCL','Uttar Pradesh',?,?,?,?,?,?,?,?,?,?,?,?,?,?, now())""",
                          [r["firm"], r["address"], r["what"], r["drug"], r["reason"], r["order"], r["date"], r["years"], r["doc"],
                           cid, pid, ",".join(map(str, mids)) or None, self.URL, key])
                self.stats.rows_new += 1
                if r["date"] and (date.today() - r["date"]).days <= 120:
                    self.emit(w, kind="nsq", severity="high", ts=r["date"],
                              title=f"UP blacklists {r['firm']} for {r['years']:g} yr: {r['drug'][:100]}" if r["years"] else f"UP blacklists {r['firm']}: {r['drug'][:100]}",
                              body=r["reason"], url=r["doc"] or self.URL, entity_type="company" if cid else None, entity_id=cid,
                              dedupe_key=f"debar|{key}", payload={"molecule_ids": mids, "state": "Uttar Pradesh"})


def doc_url(href: str) -> str | None:
    """UPMSCL links carry JSON-escaped slashes (a backslash before each slash) and raw spaces."""
    from urllib.parse import quote
    href = (href or "").replace("\\", "").strip()
    if not href:
        return None
    return "https://upmsc.in" + quote(href if href.startswith("/") else "/" + href, safe="/:%")


class PvpiAlerts(Connector):
    name = "pvpi_alerts"
    title = "PvPI Drug Safety Alerts (IPC)"
    agency = "IPC / PvPI"
    schedule = {"trigger": "cron", "day_of_week": "mon", "hour": 9, "minute": 50}
    description = "Every drug-safety alert issued by India's Pharmacovigilance Programme since March 2016: drug, indication, adverse reaction."
    URL = "https://ipc.gov.in/images/pvpi/List-of-drug-safety-alerts-issued-by-PvPI.pdf"

    def run(self):
        import io
        import pdfplumber
        pdf = self.get(self.URL, timeout=120).content
        self.archive(pdf, "pdf", key=f"pvpi-{date.today():%Y%m%d}")
        rows, month, pending, waiting = [], None, "", []
        with pdfplumber.open(io.BytesIO(pdf)) as p:
            for page in p.pages:
                for table in page.extract_tables():
                    for raw in table:
                        c = [re.sub(r"\s+", " ", (x or "")).strip() for x in raw]
                        if len(c) < 5 or not c[0].isdigit():
                            continue
                        if c[1]:
                            pending = (pending + " " + c[1]).strip() if pending and re.fullmatch(r"\d{4}", c[1]) else c[1]
                            d = pvpi_date(pending)
                            if d:
                                month, pending = d, ""
                                for r_ in waiting:          # rows that started under the incomplete date
                                    r_["month"] = d
                                waiting = []
                            elif not re.search(r"\d{4}|-\d{2}$", pending):
                                month = None    # "12th February" — the year is on the next row
                            else:
                                raise RuntimeError(f"unparsed PvPI issue date {pending!r} (row {c[0]})")
                        rows.append({"sno": int(c[0]), "month": month, "drug": fix_mojibake(c[2]), "indication": c[3] or None,
                                     "reaction": fix_mojibake(c[4])})
                        if pending:
                            waiting.append(rows[-1])
        self.stats.rows_seen = len(rows)
        if len(rows) < 100:
            raise RuntimeError(f"PvPI list parse looks wrong ({len(rows)} rows)")
        with db.writer() as w:
            for r in rows:
                key = norm(f"pvpi|{r['drug']}|{r['reaction']}")
                if w.execute("SELECT 1 FROM pvpi_alerts WHERE dedupe_key = ?", [key]).fetchall():
                    continue
                mids = matcher.molecules_in(r["drug"].replace("/", " / "), limit=4)
                w.execute("""INSERT INTO pvpi_alerts (sno, issue_month, drug_text, indication, reaction, molecule_ids, source_url, dedupe_key, fetched_at)
                             VALUES (?,?,?,?,?,?,?,?, now())""",
                          [r["sno"], r["month"], r["drug"], r["indication"], r["reaction"], ",".join(map(str, mids)) or None, self.URL, key])
                self.stats.rows_new += 1
                if r["month"] and (date.today() - r["month"]).days <= 120:
                    self.emit(w, kind="alert", severity="high", ts=r["month"], title=f"PvPI safety alert: {r['drug']} — {r['reaction']}",
                              body=r["indication"], url=self.URL, entity_type="molecule" if len(mids) == 1 else None,
                              entity_id=mids[0] if len(mids) == 1 else None, dedupe_key=f"pvpi|{key}", payload={"molecule_ids": mids})


def pvpi_date(s: str) -> date | None:
    """'Mar-16', 'December 2016', '17th October 2017', '31st August, 2020' -> date (day kept when given)."""
    t = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", s.replace(",", " "), flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    for fmt in ("%b-%y", "%d %B %Y", "%d %b %Y", "%B %Y", "%b %Y"):
        try:
            return datetime.strptime(t.title() if "%" in fmt else t, fmt).date()
        except ValueError:
            continue
    return None
