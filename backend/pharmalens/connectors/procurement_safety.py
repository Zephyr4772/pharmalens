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
