"""Approvals, pipeline and essential-medicine feeds.

* cdsco_approvals  — CDSCO "New Drugs Approved" yearly lists (drug, indication, approval date).
* cdsco_sec        — Subject Expert Committee recommendations: every agenda item (clinical-trial
                     permissions, marketing permissions, BE/Phase-III waivers) with firm and outcome.
* nlem             — National List of Essential Medicines 2022 (sets molecules.is_nlem).
* ctgov_india      — Clinical trials with Indian sites from ClinicalTrials.gov API v2 (CTRI itself
                     is CAPTCHA-gated; CTRI ids are taken from cross-registration identifiers).
* nppa_compendium  — NPPA Compendium of Prices: current ceiling prices from the IPDMS dashboard.
"""
import io
import re
from datetime import date, datetime, timedelta

import httpx
import pdfplumber
from selectolax.lexbor import LexborHTMLParser

from .. import db, matcher
from ..normalize import fix_mojibake, molecule_key, norm
from .base import BROWSER_UA, Connector
from .cdsco import CDSCO, cdsco_listing, parse_cdsco_date


def cdsco_file(conn: Connector, download_url: str) -> bytes | None:
    """CDSCO download links return a small HTML wrapper naming the real file. The file server
    drops reused keep-alive connections, so the file itself is fetched on a fresh connection."""
    r = conn.get(download_url)
    if r.content.startswith(b"%PDF"):
        return r.content
    m = re.search(r"""src=['"]([^'"]+\.pdf)['"]""", r.text, re.I) or re.search(r"<!--\s*(/opencms[^>]+?\.pdf)\s*-->", r.text, re.I)
    if not m:
        return None
    url = CDSCO + m.group(1).replace(" ", "%20")
    for attempt in range(3):
        try:
            f = httpx.get(url, headers={"User-Agent": BROWSER_UA, "Connection": "close"}, timeout=90, verify=False)
            if f.status_code == 200 and f.content.startswith(b"%PDF"):
                return f.content
        except httpx.HTTPError:
            pass
    return None


def dmy(s: str | None) -> date | None:
    if not s:
        return None
    m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", re.sub(r"\s+", "", s))
    if not m:
        return None
    d, mo, y = map(int, m.groups())
    y = y + 2000 if y < 100 else y
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def ids_str(ids: list[int]) -> str | None:
    return ",".join(map(str, ids)) or None


# ------------------------------------------------------------------ CDSCO new drug approvals
class CdscoApprovals(Connector):
    name = "cdsco_approvals"
    title = "CDSCO New Drugs Approved"
    agency = "CDSCO"
    schedule = {"trigger": "cron", "hour": 9, "minute": 25}
    description = "Yearly CDSCO lists of new drugs approved for marketing in India, with indication and approval date."
    backfill_from_year = 2015

    def run(self):
        items = cdsco_listing(self, "/opencms/opencms/en/Approval_new/Approved-New-Drugs/")
        cur = db.cursor()
        seen = {r[0] for r in cur.execute("SELECT url FROM reg_documents WHERE doc_type = 'new_drug_list'").fetchall()}
        this_year = date.today().year
        for it in items:
            m = re.search(r"(19|20)\d\d", it["title"])
            year = int(m.group(0)) if m else None
            if not year or year < self.backfill_from_year:
                continue
            # the current-year list is re-issued as approvals accrue, so it is always re-read
            if it["url"] in seen and year < this_year - 1:
                continue
            pdf = cdsco_file(self, it["url"])
            if not pdf:
                self.stats.notes.append(f"no pdf {year}")
                continue
            self.archive(pdf, "pdf")
            rows = self.parse(pdf)
            self.stats.rows_seen += len(rows)
            with db.writer() as w:
                for r in rows:
                    key = norm(f"{r['drug']}|{r['date']}")
                    if w.execute("SELECT 1 FROM reg_approvals WHERE dedupe_key = ?", [key]).fetchone():
                        continue
                    mids = matcher.molecules_in(r["drug"], limit=6)
                    w.execute("""INSERT INTO reg_approvals (agency, drug_text, indication, approved_on, applicant, approval_type,
                                 source_url, molecule_ids, dedupe_key, fetched_at) VALUES ('CDSCO',?,?,?,NULL,'new_drug',?,?,?, now())""",
                              [r["drug"], r["indication"], r["date"], it["url"], ids_str(mids), key])
                    self.stats.rows_new += 1
                    if r["date"] and (date.today() - r["date"]).days <= 365:
                        self.emit(w, kind="approval", severity="medium", ts=r["date"],
                                  title=f"CDSCO new drug approval: {r['drug'][:160]}", body=r["indication"],
                                  url=it["url"], entity_type="molecule" if len(mids) == 1 else None,
                                  entity_id=mids[0] if len(mids) == 1 else None, dedupe_key=f"appr|{key}")
                w.execute("INSERT OR IGNORE INTO reg_documents (agency, doc_type, title, published_on, url, dedupe_key, fetched_at) VALUES ('CDSCO','new_drug_list',?,?,?,?, now())",
                          [it["title"], it["date"], it["url"], f"ndl|{it['url']}"])

    @staticmethod
    def parse(pdf: bytes) -> list[dict]:
        recs: list[dict] = []
        with pdfplumber.open(io.BytesIO(pdf)) as p:
            for page in p.pages:
                for table in page.extract_tables():
                    for raw in table:
                        cells = [(c or "").replace("\n", " ").strip() for c in raw]
                        if len(cells) < 3 or norm(cells[1]).startswith("name of"):
                            continue
                        if re.match(r"^\d+\.?$", cells[0]):
                            recs.append({"drug": [cells[1]], "ind": [cells[2] if len(cells) > 3 else ""], "dt": [cells[-1]]})
                        elif not cells[0] and recs:
                            recs[-1]["drug"].append(cells[1])
                            if len(cells) > 3:
                                recs[-1]["ind"].append(cells[2])
                            recs[-1]["dt"].append(cells[-1])
        out = []
        for r in recs:
            drug = re.sub(r"\s+", " ", " ".join(x for x in r["drug"] if x)).strip()
            if not drug:
                continue
            out.append({"drug": fix_mojibake(drug), "indication": fix_mojibake(re.sub(r"\s+", " ", " ".join(x for x in r["ind"] if x)).strip()) or None,
                        "date": dmy(" ".join(r["dt"]))})
        return out


# ------------------------------------------------------------------ SEC recommendations
OUTCOMES = [
    ("not_recommended", r"not recommend|did not recommend|rejected|not accepted|not justified|not approved|denied"),
    ("recommended", r"recommended for (the )?grant|recommended (the )?grant|recommended for approval|recommended to grant|recommended for permission|committee recommended|recommended for waiver|recommended the"),
    ("deferred", r"required to submit|should submit|further review|deferred|directed|opined that the firm|asked the firm|to present|clarif"),
]
DIVISIONS = [
    ("clinical_trial", r"\bgct\b|clinical trial|\bct division"),
    ("new_drug", r"new drug|\bsnd\b|subsequent new"),
    ("be", r"\bbe division|bioequivalence"),
    ("biological", r"biolog|vaccine|rdna"),
    ("medical_device", r"device"),
    ("fdc", r"\bfdc\b|fixed dose"),
]


def classify(text: str, table: list[tuple[str, str]]) -> str | None:
    t = text.lower()
    for name, rx in table:
        if re.search(rx, t):
            return name
    return None


FILE_PREFIX_DIVISION = {"CT": "clinical_trial", "GCT": "clinical_trial", "ND": "new_drug", "SND": "new_drug", "BE": "be",
                        "BABE": "be", "BA": "be", "BIO": "biological", "MD": "medical_device", "FDC": "fdc", "IMP": "import"}


def refine_division(division: str, drug: str, rec: str, committee: str) -> str:
    """Fallback when the agenda row carries no recognisable file prefix."""
    if division != "other":
        return division
    t = f"{drug} {rec}".lower()
    if "vaccine" in (committee or "").lower() or re.search(r"r-?dna|vaccine|biosimilar|monoclonal|\bmab\b", t):
        return "biological"
    if re.search(r"\bphase\s*(i|ii|iii|iv|1|2|3|4)\b|protocol|clinical (trial|study)", t):
        return "clinical_trial"
    if re.search(r"bioequivalence|\bbe study", t):
        return "be"
    if re.search(r"\bfdc\b|fixed dose", t):
        return "fdc"
    if re.search(r"manufacture and market|marketing authori|permission to (manufacture|import)", t):
        return "new_drug"
    return division


def split_file_no(text: str, division: str | None) -> tuple[str | None, str, str]:
    """'BIO/CT04/FF/2025/ 52727 Lecanemab ...' -> ('BIO/CT04/FF/2025/52727', 'Lecanemab ...', 'biological').
    File numbers wrap across PDF lines, and SND items repeat the MA number in brackets."""
    fm = re.match(r"^((?:[A-Z]{1,5}/)[\w/.\-]*)\s*(?:Online\s*Submission)?\s*", text)
    if not fm:
        return None, text, division or "other"
    file_no, drug = fm.group(1), text[fm.end():]
    m = re.match(r"^(\d{1,6})\b\s*", drug)
    if m and (file_no.endswith("/") or re.search(r"/\d{1,4}$", file_no)):
        file_no = file_no.rstrip("/") + "/" + m.group(1) if file_no.endswith("/") else file_no + m.group(1)
        drug = drug[m.end():]
    drug = re.sub(r"^(?:\(\s*\d+\s*\)|\(\s*[A-Z]{1,5}/[^)]*\))\s*", "", drug)
    drug = re.sub(r"^(?:\(\s*\d+\s*\)|\(\s*[A-Z]{1,5}/[^)]*\))\s*", "", drug)
    division = FILE_PREFIX_DIVISION.get(file_no.split("/")[0].upper(), division) or "other"
    return file_no, drug.strip() or text, division


class CdscoSec(Connector):
    name = "cdsco_sec"
    title = "CDSCO Subject Expert Committee Recommendations"
    agency = "CDSCO"
    schedule = {"trigger": "cron", "hour": "11,18", "minute": 45}
    description = ("Every SEC agenda item: clinical-trial permissions, marketing permissions, BE/Phase-III waivers — "
                   "drug, firm, committee and outcome. The forward pipeline of what is about to launch in India.")
    backfill_days = 540

    def run(self):
        html = self.get(CDSCO + "/opencms/opencms/en/Committees/SEC/").text
        items = []
        for tr in LexborHTMLParser(html).css("table tr"):
            tds = tr.css("td")
            a = tr.css_first("a[href*=num_id_pk]")
            if len(tds) >= 4 and a:
                items.append({"title": fix_mojibake(tds[1].text(strip=True)), "date": parse_cdsco_date(tds[2].text(strip=True)),
                              "committee": tds[3].text(strip=True), "url": CDSCO + a.attributes["href"]})
        cur = db.cursor()
        seen = {r[0] for r in cur.execute("SELECT url FROM reg_documents WHERE doc_type = 'sec_recommendation'").fetchall()}
        cutoff = date.today() - timedelta(days=self.backfill_days)
        todo = [i for i in items if i["url"] not in seen and i["date"] and i["date"] >= cutoff]
        self.stats.notes.append(f"{len(todo)} new documents")
        for it in sorted(todo, key=lambda x: x["date"]):
            pdf = cdsco_file(self, it["url"])
            with db.writer() as w:
                w.execute("INSERT OR IGNORE INTO reg_documents (agency, doc_type, title, published_on, url, dedupe_key, fetched_at) VALUES ('CDSCO','sec_recommendation',?,?,?,?, now())",
                          [f"{it['committee']}: {it['title']}", it["date"], it["url"], f"sec|{it['url']}"])
            if not pdf:
                continue
            self.archive(pdf, "pdf")
            hm = re.search(r"held on\s*([\d./-]+)", it["title"])
            meeting = dmy(hm.group(1)) if hm else None
            if not meeting or meeting.year < 2000 or meeting > it["date"]:
                meeting = it["date"]   # titles are truncated on the listing page
            rows = self.parse(pdf)
            self.stats.rows_seen += len(rows)
            with db.writer() as w:
                for r in rows:
                    key = norm(f"{it['url']}|{r['file_no']}|{r['drug'][:80]}")
                    if w.execute("SELECT 1 FROM sec_items WHERE dedupe_key = ?", [key]).fetchone():
                        continue
                    mids = matcher.molecules_in(r["drug"], limit=6)
                    cid = matcher.company_for(r["firm"])
                    pid = matcher.parent_for(re.sub(r"^\s*m\s*/\s*s\.?\s*", "", r["firm"] or "", flags=re.I))
                    if not r["drug"].strip() and not r["rec"].strip():
                        continue
                    r["division"] = refine_division(r["division"], r["drug"], r["rec"], it["committee"])
                    outcome = classify(r["rec"], OUTCOMES) or "noted"
                    w.execute("""INSERT INTO sec_items (meeting_date, committee, division, file_no, drug_text, firm, recommendation,
                                 outcome, molecule_ids, company_id, parent_id, source_url, dedupe_key, fetched_at)
                                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, now())""",
                              [meeting, it["committee"], r["division"], r["file_no"], r["drug"], r["firm"], r["rec"][:4000],
                               outcome, ids_str(mids), cid, pid, it["url"], key])
                    self.stats.rows_new += 1
                    recent = meeting and (date.today() - meeting).days <= 120
                    if recent and outcome == "recommended" and (r["division"] in ("new_drug", "biological", "fdc") or pid):
                        what = {"new_drug": "marketing permission", "clinical_trial": "trial permission", "fdc": "FDC permission",
                                "biological": "biological approval", "be": "BE study"}.get(r["division"], "approval")
                        self.emit(w, kind="approval", severity="medium", ts=meeting,
                                  title=f"SEC recommends {what}: {r['drug'][:120]} — {(r['firm'] or '').strip()[:60]}",
                                  body=r["rec"][:600], url=it["url"], entity_type="parent" if pid else None, entity_id=pid,
                                  dedupe_key=f"sec|{key}", payload={"committee": it["committee"], "outcome": outcome})

    @staticmethod
    def parse(pdf: bytes) -> list[dict]:
        recs: list[dict] = []
        division = None
        with pdfplumber.open(io.BytesIO(pdf)) as p:
            for page in p.pages:
                for table in page.extract_tables():
                    for raw in table:
                        cells = [(c or "").replace("\n", " ").strip() for c in raw]
                        if len(cells) < 4:
                            continue
                        joined = " ".join(cells)
                        if not cells[0] and cells[1] and not any(cells[2:]) and len(cells[1]) < 60:
                            division = classify(cells[1], DIVISIONS) or division   # "GCT Division" header row
                            continue
                        if norm(cells[0]).startswith(("s no", "sl no", "s no ")) or "recommendation" in norm(cells[-1])[:20]:
                            continue
                        if re.match(r"^\d+\.?$", cells[0]):
                            recs.append({"drug": cells[1], "firm": cells[2], "rec": [cells[3]], "division": division})
                        elif recs and not cells[0] and joined.strip():
                            # continuation across a page break
                            if cells[1]:
                                recs[-1]["drug"] += " " + cells[1]
                            if cells[2]:
                                recs[-1]["firm"] += " " + cells[2]
                            recs[-1]["rec"].append(cells[3])
        out = []
        for r in recs:
            raw_drug = re.sub(r"\s+", " ", r["drug"]).strip()
            file_no, drug, division = split_file_no(raw_drug, r["division"])
            out.append({"file_no": file_no, "drug": fix_mojibake(drug) or raw_drug, "firm": fix_mojibake(re.sub(r"\s+", " ", r["firm"]).strip()),
                        "rec": fix_mojibake(re.sub(r"\s+", " ", " ".join(r["rec"])).strip()), "division": division or "other"})
        return out


# ------------------------------------------------------------------ NLEM 2022
class Nlem(Connector):
    name = "nlem"
    title = "National List of Essential Medicines 2022"
    agency = "MoHFW / NPPA"
    schedule = {"trigger": "cron", "day": 1, "hour": 6, "minute": 0}
    description = "NLEM 2022: essential medicines with level of care (P/S/T) and dosage forms; drives price control under DPCO."
    URL = "https://nppa.gov.in/storage/uploads/pdf/nlem-2022pdf-0cd1d2b28855bf30128875ab19fc5304.pdf"

    def run(self):
        page = self.get("https://nppa.gov.in/en/nlem2022").text
        m = re.search(r'href="(https://nppa\.gov\.in/storage/uploads/pdf/nlem-2022[^"]+\.pdf)"', page)
        url = m.group(1) if m else self.URL
        r = self.get(url)
        if not r.content.startswith(b"%PDF"):
            raise RuntimeError("NLEM pdf not found")
        self.archive(r.content, "pdf", key="nlem2022")
        rows = self.parse(r.content)
        self.stats.rows_seen = len(rows)
        if len(rows) < 300:
            raise RuntimeError(f"NLEM parse looks wrong ({len(rows)} rows)")
        with db.writer() as w:
            w.execute("DELETE FROM nlem WHERE edition = '2022'")
            for x in rows:
                mids = matcher.molecules_in(x["medicine"], limit=4) or []
                if not mids:
                    k = molecule_key(re.sub(r"\(.*?\)|\*", " ", x["medicine"]))
                    hit = w.execute("SELECT id FROM molecules WHERE mkey = ?", [k]).fetchone()
                    mids = [hit[0]] if hit else []
                for mid in (mids or [None]):
                    w.execute("INSERT INTO nlem VALUES (?,?,?,?,?, '2022')", [x["medicine"], mid, x["section"], x["level"], x["dosage"]])
                    self.stats.rows_new += 1

    @staticmethod
    def parse(pdf: bytes) -> list[dict]:
        out, section = [], None
        with pdfplumber.open(io.BytesIO(pdf)) as p:
            for page in p.pages:
                txt = page.extract_text() or ""
                if not re.search(r"[A-Za-z]{4,}", txt) or "Level of" not in txt and "Medicine" not in txt and "Section" not in txt:
                    continue
                for table in page.extract_tables():
                    for raw in table:
                        cells = [(c or "").replace("\n", " ").strip() for c in raw]
                        if not cells:
                            continue
                        if re.match(r"^Section\s+\d", cells[0]):
                            section = re.sub(r"\s+", " ", cells[0])
                            continue
                        if len(cells) >= 4 and re.match(r"^\d+(\.\d+)+$", cells[0]) and re.search(r"[A-Za-z]{3,}", cells[1]):
                            med = re.sub(r"\*+", "", cells[1]).strip()
                            out.append({"medicine": med, "section": section, "level": cells[2], "dosage": cells[3]})
        return out


# ------------------------------------------------------------------ ClinicalTrials.gov (India sites)
CTGOV = "https://clinicaltrials.gov/api/v2/studies"
CT_FIELDS = ("NCTId,BriefTitle,LeadSponsorName,LeadSponsorClass,Phase,OverallStatus,Condition,InterventionName,"
             "InterventionType,StartDate,PrimaryCompletionDate,LastUpdatePostDate,EnrollmentCount,SecondaryId,LocationCountry")


class ClinicalTrialsIndia(Connector):
    name = "ctgov_india"
    title = "Clinical Trials with Indian Sites"
    agency = "ClinicalTrials.gov"
    schedule = {"trigger": "cron", "hour": 5, "minute": 40}
    description = "Interventional trials recruiting or running at Indian sites (ClinicalTrials.gov API v2), with CTRI cross-registration ids."

    def run(self):
        cur = db.cursor()
        last = cur.execute("SELECT max(last_update) FROM trials").fetchone()[0]
        since = (last - timedelta(days=3)) if last else date.today() - timedelta(days=3 * 365)
        params = {
            "query.locn": "India", "query.term": f"AREA[LastUpdatePostDate]RANGE[{since.isoformat()},MAX] AND AREA[StudyType]INTERVENTIONAL",
            "pageSize": 1000, "fields": CT_FIELDS, "format": "json",
        }
        first_load = last is None
        token = None
        while True:
            if token:
                params["pageToken"] = token
            r = self.get(CTGOV, params=params)
            r.raise_for_status()
            d = r.json()
            studies = d.get("studies", [])
            with db.writer() as w:
                for s in studies:
                    self._upsert(w, s, first_load)
            token = d.get("nextPageToken")
            if not token or self.stats.rows_seen > 20000:
                break

    def _upsert(self, w, s: dict, first_load: bool):
        p = s.get("protocolSection", {})
        ident = p.get("identificationModule", {})
        nct = ident.get("nctId")
        if not nct:
            return
        self.stats.rows_seen += 1
        status = p.get("statusModule", {})
        spons = p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {})
        design = p.get("designModule", {})
        arms = p.get("armsInterventionsModule", {}).get("interventions", []) or []
        drugs = [i.get("name", "") for i in arms if i.get("type") in ("DRUG", "BIOLOGICAL", "COMBINATION_PRODUCT", None)]
        locs = p.get("contactsLocationsModule", {}).get("locations", []) or []
        india = sum(1 for l in locs if (l.get("country") or "").lower() == "india")
        sec_ids = [x.get("id", "") for x in ident.get("secondaryIdInfos", []) or []]
        ctri = next((x for x in sec_ids if x.upper().startswith("CTRI")), None)
        mids = []
        for dname in drugs[:6]:
            for m in matcher.molecules_in(dname, limit=3):
                if m not in mids:
                    mids.append(m)
        sponsor = spons.get("name")
        pid = matcher.parent_for(sponsor, region="global") or (matcher.parents_in(sponsor or "") or [None])[0]
        exists = w.execute("SELECT status FROM trials WHERE nct_id = ?", [nct]).fetchone()
        upd = status.get("lastUpdatePostDateStruct", {}).get("date")
        w.execute("INSERT OR REPLACE INTO trials VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, now())", [
            nct, ctri, ident.get("briefTitle"), sponsor, spons.get("class"), ",".join(design.get("phases", []) or []) or None,
            status.get("overallStatus"), "; ".join(p.get("conditionsModule", {}).get("conditions", []) or [])[:600],
            "; ".join(drugs)[:600], status.get("startDateStruct", {}).get("date"),
            status.get("primaryCompletionDateStruct", {}).get("date"), india or None,
            (design.get("enrollmentInfo") or {}).get("count"), upd, ids_str(mids), pid])
        if not exists:
            self.stats.rows_new += 1
            phases = design.get("phases", []) or []
            if not first_load and (pid or "PHASE3" in phases):
                self.emit(w, kind="trial", severity="info", ts=upd,
                          title=f"New trial in India: {ident.get('briefTitle', '')[:150]} — {sponsor}",
                          url=f"https://clinicaltrials.gov/study/{nct}", entity_type="parent" if pid else None,
                          entity_id=pid, dedupe_key=f"ct|{nct}", payload={"phase": phases, "ctri": ctri})


# ------------------------------------------------------------------ NPPA compendium of prices
PRICE_RX = re.compile(r"([\d,]+(?:\.\d+)?)\s*\((.*)\)\s*$")


class NppaCompendium(Connector):
    name = "nppa_compendium"
    title = "NPPA Compendium of Prices (ceiling prices)"
    agency = "NPPA"
    schedule = {"trigger": "cron", "day_of_week": "tue", "hour": 10, "minute": 40}
    description = "Current DPCO ceiling price of every scheduled formulation, plus company-specific special-feature prices (NPPA IPDMS dashboard)."

    def run(self):
        from .nppa_dashboard import WIDGETS, NppaDashboard
        nd = NppaDashboard()
        try:
            rows = []
            for kind, wid in WIDGETS.items():
                html = nd.widget(wid).get("HTML", "")
                self.archive(html, "html", key=f"compendium-{kind}-{date.today():%Y%m%d}")
                for tr in LexborHTMLParser(html).css("tbody tr"):
                    c = [td.text(strip=True) for td in tr.css("td")]
                    if kind == "ceiling" and len(c) >= 7:
                        rows.append({"kind": kind, "nlem": c[1], "name": c[2], "form": c[3], "so": c[4], "so_date": c[5], "price": c[6]})
                    elif kind == "special" and len(c) >= 6:
                        rows.append({"kind": kind, "nlem": None, "name": c[1], "form": c[2], "so": c[3], "so_date": c[4], "price": c[5]})
        finally:
            nd.close()
        self.stats.rows_seen = len(rows)
        if len(rows) < 500:
            raise RuntimeError(f"compendium returned only {len(rows)} rows")
        with db.writer() as w:
            prev = {f"{a}|{b}|{u}": p for a, b, u, p in w.execute(
                "SELECT molecule_name, form_strength, unit, ceiling_price FROM nppa_ceiling WHERE source LIKE 'NPPA%'").fetchall()}
            w.execute("DELETE FROM nppa_ceiling")   # official compendium supersedes the dataset copy
            changes = 0
            for i, r in enumerate(rows, start=1):
                m = PRICE_RX.search(r["price"].replace("₹", "").strip())
                price = float(m.group(1).replace(",", "")) if m else None
                unit = m.group(2).strip() if m else None
                name = fix_mojibake(r["name"])
                mono = "+" not in name
                mid = None
                if mono:
                    k = molecule_key(re.sub(r"\(.*?\)", " ", name))
                    hit = w.execute("SELECT id FROM molecules WHERE mkey = ?", [k]).fetchone()
                    mid = hit[0] if hit else (matcher.molecules_in(name, limit=1) or [None])[0]
                so_date = None
                try:
                    so_date = datetime.strptime(r["so_date"], "%d-%b-%Y").date()
                except ValueError:
                    pass
                notif = f"S.O. {r['so']} dt {r['so_date']}" + (" (special feature)" if r["kind"] == "special" else "")
                w.execute("INSERT INTO nppa_ceiling VALUES (?,?,?,?,?,?,?,?,?)",
                          [i, mid, name, r["form"], price, unit, notif, int(r["nlem"]) if (r["nlem"] or "").isdigit() else (so_date.year if so_date else None),
                           f"NPPA compendium {r['kind']} {date.today():%Y-%m-%d}"])
                key = f"{name}|{r['form']}|{unit}"
                if prev and key in prev and price and prev[key] and abs(prev[key] - price) > 0.005:
                    changes += 1
                    self.emit(w, kind="price_notification", severity="high", ts=so_date,
                              title=f"NPPA ceiling revised: {name} {r['form']} ₹{prev[key]} → ₹{price} ({unit})",
                              entity_type="molecule" if mid else None, entity_id=mid,
                              dedupe_key=f"ceil|{key}|{price}", payload={"old": prev[key], "new": price, "so": r["so"]})
            self.stats.rows_new = len(rows) if not prev else changes
            self.stats.notes.append(f"{changes} price changes" if prev else "first official load")
