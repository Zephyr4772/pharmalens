"""NPPA (pricing regulator) and PMBI Jan Aushadhi connectors."""
import re
from datetime import date, datetime

from selectolax.lexbor import LexborHTMLParser

from .. import db, matcher
from .base import Connector

NPPA = "https://nppa.gov.in/en/"


def nppa_date(s: str) -> date | None:
    for fmt in ("%d-%b-%Y", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None


def minutes_date(title: str) -> date | None:
    m = re.search(r"held on (\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", title)
    if not m:
        return None
    d, mo, y = map(int, m.groups())
    y = y + 2000 if y < 100 else y
    try:
        return date(y, mo, d)
    except ValueError:
        return None


class NppaOrders(Connector):
    name = "nppa_orders"
    title = "NPPA Orders, Circulars & Authority Minutes"
    agency = "NPPA"
    schedule = {"trigger": "cron", "hour": "10,17", "minute": 15}
    description = ("Drug price circulars/orders, draft price calculation sheets (new retail prices), "
                   "DPCO Authority meeting minutes, overcharging case status.")

    def _listing(self, path: str) -> list[dict]:
        html = self.get(NPPA + path).text
        out = []
        for tr in LexborHTMLParser(html).css("table tr"):
            tds = [td.text(strip=True) for td in tr.css("td")]
            a = tr.css_first("a[href$='.pdf'], a[href*='storage/uploads']")
            if not tds or not a:
                continue
            href = a.attributes.get("href")
            if "nppaipdms" in (href or ""):
                continue
            if len(tds) >= 4:     # Sr, Date, Title, Attachment
                out.append({"date": nppa_date(tds[1]), "title": tds[2], "url": href})
            elif len(tds) >= 2:   # Document Name, Download (year pages)
                t = tds[0] if not tds[0].isdigit() else tds[1]
                out.append({"date": minutes_date(t), "title": t, "url": href})
        return out

    def run(self):
        sources = [("view_more?id=4", "order")]
        y = date.today().year
        for fy in (f"year{y}", f"year{y - 1}-{y}", f"year{y}-{y + 1}"):
            sources.append((fy, "authority_minutes"))
        for path, doc_type in sources:
            try:
                items = self._listing(path)
            except Exception as e:  # noqa: BLE001
                self.stats.notes.append(f"{path}: {e}")
                continue
            self.stats.rows_seen += len(items)
            with db.writer() as cur:
                for it in items:
                    key = f"doc|{it['url']}"
                    if cur.execute("SELECT 1 FROM reg_documents WHERE dedupe_key = ?", [key]).fetchone():
                        continue
                    t = it["title"]
                    dt = doc_type
                    if "overcharg" in t.lower():
                        dt = "overcharging"
                    elif "price calculation" in t.lower():
                        dt = "draft_price_sheet"
                    cur.execute(
                        "INSERT INTO reg_documents (agency, doc_type, title, published_on, url, dedupe_key, fetched_at) VALUES (?,?,?,?,?,?, now())",
                        ["NPPA", dt, t, it["date"], it["url"], key],
                    )
                    self.stats.rows_new += 1
                    if it["date"] and (date.today() - it["date"]).days <= 400:
                        self.emit(cur, kind="price_notification", severity="medium", ts=it["date"],
                                  title=f"NPPA: {t[:220]}", url=it["url"], dedupe_key=key,
                                  payload={"doc_type": dt})


class JanAushadhi(Connector):
    name = "jan_aushadhi"
    title = "PMBI Jan Aushadhi Product & MRP List"
    agency = "PMBI"
    schedule = {"trigger": "cron", "day_of_week": "mon,thu", "hour": 11, "minute": 0}
    description = "Every generic sold through Pradhan Mantri Bhartiya Janaushadhi Kendras with its MRP."
    BASE = "https://janaushadhi.gov.in:8443/"

    def run(self):
        hdr = {"Origin": "https://janaushadhi.gov.in", "Referer": "https://janaushadhi.gov.in/"}
        tok = self.http.get(self.BASE + "auth/generateGuestToken", headers=hdr).json()["responseBody"]
        r = self.http.post(
            self.BASE + "api/v1/website/getAllProductForWeb",
            json={"pageIndex": 0, "pageSize": 1000000, "searchText": "", "orderBy": "asc", "columnName": "drug_code"},
            headers={**hdr, "Authorization": f"Bearer {tok}"},
        )
        r.raise_for_status()
        self.archive(r.content, "json")
        items = r.json()["responseBody"]["newProductResponsesList"]
        self.stats.rows_seen = len(items)
        with db.writer() as cur:
            prev = dict(cur.execute("SELECT drug_code, mrp FROM jan_aushadhi").fetchall())
            first_load = not prev
            for it in items:
                code = str(it.get("drugCode"))
                name = (it.get("genericName") or "").strip()
                mrp = it.get("mrp")
                mids = matcher.molecules_in(name)
                cur.execute(
                    """INSERT OR REPLACE INTO jan_aushadhi (drug_code, name, unit_size, mrp, group_name, molecule_ids, fetched_at)
                       VALUES (?,?,?,?,?,?, now())""",
                    [code, name, it.get("unitSize"), mrp, it.get("groupName"), ",".join(map(str, mids)) or None],
                )
                if code not in prev:
                    self.stats.rows_new += 1
                    if not first_load:
                        self.emit(cur, kind="launch", severity="info", title=f"Jan Aushadhi adds {name} ({it.get('unitSize')}) at ₹{mrp}",
                                  url="https://janaushadhi.gov.in/product-portfolio/product-mrp-list",
                                  entity_type="molecule" if len(mids) == 1 else None, entity_id=mids[0] if len(mids) == 1 else None,
                                  dedupe_key=f"ja|new|{code}")
                elif mrp and prev[code] and abs(float(mrp) - float(prev[code])) > 0.009:
                    self.emit(cur, kind="price_notification", severity="info",
                              title=f"Jan Aushadhi MRP change: {name} ₹{prev[code]} → ₹{mrp}",
                              dedupe_key=f"ja|mrp|{code}|{mrp}", payload={"old": prev[code], "new": mrp})
