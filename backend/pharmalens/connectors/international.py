"""International regulators — where Indian manufacturers sell and get inspected.

* openfda_bulk   — Drugs@FDA applications, Orange Book (with patents + exclusivities), NDC directory and
                   current US shortages from openFDA's daily bulk export. Indian groups are linked via
                   sponsor / labeler names.
* who_pq         — WHO prequalified finished pharmaceutical products (applicant, INN, area, date).
* ema_medicines  — EU centrally authorised medicines register (incl. generics/biosimilars by Indian MAHs).
* nse_filings    — NSE corporate announcements for every listed group we track (results, USFDA
                   observations, M&A, plant events), tagged by topic.
"""
import csv
import io
import json
import re
import zipfile
from datetime import date, datetime

import pandas as pd

from .. import db, matcher
from ..normalize import norm
from .base import BROWSER_UA, Connector

OPENFDA = "https://download.open.fda.gov/drug/{k}/drug-{k}-0001-of-0001.json.zip"


def ymd(s: str | None) -> date | None:
    try:
        return datetime.strptime(s, "%Y%m%d").date() if s else None
    except ValueError:
        return None


def mids_for(names: list[str]) -> str | None:
    out = []
    for n in names:
        for m in matcher.molecules_in(n or "", limit=4):
            if m not in out:
                out.append(m)
    return ",".join(map(str, out)) or None


class OpenFdaBulk(Connector):
    name = "openfda_bulk"
    title = "US FDA Approvals, Orange Book, NDC & Shortages"
    agency = "US FDA (openFDA)"
    schedule = {"trigger": "cron", "day_of_week": "mon,thu", "hour": 6, "minute": 10}
    description = ("Drugs@FDA applications, Orange Book products with patents and exclusivities, the NDC directory and current "
                   "US shortages; Indian groups linked by sponsor/labeler.")

    def load(self, k: str) -> list[dict]:
        r = self.get(OPENFDA.format(k=k), timeout=600)
        r.raise_for_status()
        self.archive(r.content, "zip", key=f"{k}-{date.today():%Y%m%d}")
        z = zipfile.ZipFile(io.BytesIO(r.content))
        return json.loads(z.read(z.namelist()[0]))["results"]

    def run(self):
        apps = self.load("drugsfda")
        ob = self.load("orangebook")
        ndc = self.load("ndc")
        sh = self.load("shortages")
        self.stats.rows_seen = len(apps) + len(ob) + len(ndc) + len(sh)
        parent_cache: dict[str, int | None] = {}

        def parent(name: str | None) -> int | None:
            if not name:
                return None
            if name not in parent_cache:
                parent_cache[name] = matcher.parent_for(name, region="global")
            return parent_cache[name]

        app_rows = []
        for a in apps:
            prods = a.get("products") or []
            subs = a.get("submissions") or []
            approved = sorted(ymd(s.get("submission_status_date")) for s in subs
                              if s.get("submission_status") == "AP" and ymd(s.get("submission_status_date")))
            ingr = sorted({i.get("name", "") for p in prods for i in (p.get("active_ingredients") or [])})
            app_rows.append((
                a["application_number"], a.get("sponsor_name"), parent(a.get("sponsor_name")),
                re.sub(r"\d+", "", a["application_number"]),
                "; ".join(sorted({p.get("brand_name", "") for p in prods if p.get("brand_name")}))[:500],
                "; ".join(ingr)[:500], "; ".join(sorted({p.get("dosage_form", "") for p in prods if p.get("dosage_form")}))[:200],
                "; ".join(sorted({p.get("marketing_status", "") for p in prods if p.get("marketing_status")}))[:120],
                approved[0] if approved else None, approved[-1] if approved else None, len(subs), mids_for(ingr),
            ))
        ob_rows, pat_rows = [], []
        for o in ob:
            for p in o.get("products") or []:
                ingr = [i.get("name", "") for i in (p.get("active_ingredients") or [])]
                appl = p.get("application_full_name") or p.get("application_name")
                ob_rows.append((p.get("application_number"), o.get("product_number"), p.get("brand_name"), "; ".join(ingr)[:300],
                                "; ".join(i.get("strength", "") for i in (p.get("active_ingredients") or []))[:200],
                                p.get("dosage_form"), p.get("route"), p.get("application_type"), p.get("reference_listed_drug"),
                                p.get("marketing_status"), ymd(o.get("approval_date")), appl, parent(appl), mids_for(ingr)))
                for pt in o.get("patents") or []:
                    pat_rows.append((p.get("application_number"), o.get("product_number"), "patent", pt.get("patent_number"),
                                     pt.get("patent_use_code"), ymd(pt.get("expiration_date")), "; ".join(ingr)[:300], mids_for(ingr)))
                for ex in o.get("exclusivity") or []:
                    pat_rows.append((p.get("application_number"), o.get("product_number"), "exclusivity", ex.get("exclusivity_code"),
                                     None, ymd(ex.get("exclusivity_date")), "; ".join(ingr)[:300], mids_for(ingr)))
        ndc_rows = []
        for n in ndc:
            ingr = [i.get("name", "") for i in (n.get("active_ingredients") or [])]
            ndc_rows.append((n.get("product_ndc"), n.get("labeler_name"), parent(n.get("labeler_name")), n.get("brand_name"),
                             n.get("generic_name"), n.get("dosage_form"), n.get("marketing_category"), n.get("application_number"),
                             (n.get("openfda") or {}).get("manufacturer_name", [None])[0], mids_for(ingr)))
        sh_rows = []
        for i, s in enumerate(sh):
            gen = s.get("generic_name") or ""
            ofd = s.get("openfda") or {}
            try:
                upd = datetime.strptime(s.get("update_date") or "", "%m/%d/%Y").date()
            except ValueError:
                upd = None
            sh_rows.append((f"usfda-{s.get('package_ndc') or i}", "US", gen, s.get("company_name"), s.get("status"),
                            s.get("shortage_reason") or s.get("availability"), "; ".join(s.get("therapeutic_category") or []),
                            upd, "US FDA Drug Shortages (openFDA)", mids_for([gen] + (ofd.get("substance_name") or []))))

        def frame(rows, cols):
            return pd.DataFrame(rows, columns=cols)

        new_total = 0
        with db.writer() as w:
            for t, cols, rows in [
                ("us_applications", ["application_number", "sponsor", "parent_id", "app_type", "brands", "ingredients", "dosage_forms",
                                     "marketing_status", "first_approval", "last_action", "n_submissions", "molecule_ids"], app_rows),
                ("us_orange_book", ["application_number", "product_number", "brand", "ingredients", "strengths", "dosage_form", "route",
                                    "app_type", "rld", "marketing_status", "approval_date", "applicant", "parent_id", "molecule_ids"], ob_rows),
                ("us_patents", ["application_number", "product_number", "kind", "code", "use_code", "expires_on", "ingredients", "molecule_ids"], pat_rows),
                ("us_ndc", ["product_ndc", "labeler", "parent_id", "brand", "generic", "dosage_form", "marketing_category",
                            "application_number", "manufacturer", "molecule_ids"], ndc_rows),
            ]:
                # the bulk files are reloaded whole: count as new only rows whose identity was not there before
                key_cols = {"us_applications": 1, "us_orange_book": 2, "us_patents": 4, "us_ndc": 1}[t]
                before = {tuple(r) for r in w.execute(f"SELECT {', '.join(cols[:key_cols])} FROM {t}").fetchall()}
                new_total += sum(1 for r in rows if tuple(r[:key_cols]) not in before)
                w.execute(f"DELETE FROM {t}")
                df = frame(rows, cols)
                w.register("_df", df)
                w.execute(f"INSERT INTO {t} ({', '.join(cols)}) SELECT {', '.join(cols)} FROM _df")
                w.unregister("_df")
            # current US shortages replace the 2024 legacy snapshot
            had = {r[0] for r in w.execute("SELECT id FROM shortages WHERE region = 'US'").fetchall()}
            new_total += sum(1 for r in sh_rows if r[0] not in had)
            w.execute("DELETE FROM shortages WHERE region = 'US'")
            w.register("_sh", frame(sh_rows, ["id", "region", "molecule_text", "company", "status", "reason", "category", "updated_on", "source", "molecule_ids"]))
            w.execute("INSERT OR REPLACE INTO shortages SELECT * FROM _sh")
            w.unregister("_sh")
        self.stats.rows_new = new_total
        self.stats.notes.append(f"{len(app_rows):,} applications · {len(ob_rows):,} OB products · {len(pat_rows):,} patents/exclusivities · "
                                f"{len(ndc_rows):,} NDC · {len(sh_rows):,} shortages")


class WhoPrequal(Connector):
    name = "who_pq"
    title = "WHO Prequalified Medicines"
    agency = "WHO"
    schedule = {"trigger": "cron", "day_of_week": "wed", "hour": 7, "minute": 0}
    description = "WHO-prequalified finished pharmaceutical products (used by UN procurement), with applicant and date."
    URL = "https://extranet.who.int/prequal/medicines/prequalified/finished-pharmaceutical-products/export"

    def run(self):
        r = self.get(self.URL)
        r.raise_for_status()
        self.archive(r.content, "csv", key=f"who-pq-{date.today():%Y%m%d}")
        rows = list(csv.DictReader(io.StringIO(r.text)))
        self.stats.rows_seen = len(rows)
        with db.writer() as w:
            prev = {x[0] for x in w.execute("SELECT ref FROM who_pq").fetchall()}
            w.execute("DELETE FROM who_pq")
            for x in rows:
                ref = x.get("WHO Reference Number")
                when = None
                try:
                    when = datetime.strptime(re.sub(r"\s+", " ", x.get("Date of Prequalification", "")).strip(), "%d %b, %Y").date()
                except ValueError:
                    pass
                inn = x.get("INN, Dosage Form and Strength")
                pid = matcher.parent_for(x.get("Applicant"), region="global")
                w.execute("INSERT INTO who_pq VALUES (?,?,?,?,?,?,?,?,?,?)",
                          [ref, inn, x.get("Product Type"), x.get("Therapeutic Area"), x.get("Applicant"), x.get("Dosage Form"),
                           x.get("Basis of Listing"), when, pid, mids_for([inn])])
                if prev and ref not in prev:
                    self.stats.rows_new += 1
                    self.emit(w, kind="approval", severity="medium", ts=when, title=f"WHO prequalification: {inn} — {x.get('Applicant')}",
                              entity_type="parent" if pid else None, entity_id=pid, dedupe_key=f"whopq|{ref}")
            if not prev:
                self.stats.rows_new = len(rows)


class EmaMedicines(Connector):
    name = "ema_medicines"
    title = "EMA Medicines Register (EU)"
    agency = "European Medicines Agency"
    schedule = {"trigger": "cron", "day_of_week": "wed", "hour": 7, "minute": 20}
    description = "EU centrally authorised medicines: INN, holder, status, generic/biosimilar flags, dates."
    URL = "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines-report_en.xlsx"

    def run(self):
        r = self.get(self.URL, timeout=300)
        r.raise_for_status()
        self.archive(r.content, "xlsx", key=f"ema-{date.today():%Y%m%d}")
        raw = pd.read_excel(io.BytesIO(r.content), header=None)
        hdr = next(i for i in range(min(30, len(raw))) if any(str(v).strip().lower() in ("name of medicine", "medicine name") for v in raw.iloc[i]))
        df = pd.read_excel(io.BytesIO(r.content), skiprows=hdr)
        df.columns = [re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_") for c in df.columns]
        self.stats.rows_seen = len(df)
        keep = {c: c for c in df.columns}
        holder_col = next((c for c in df.columns if "marketing_authorisation" in c and ("holder" in c or "developer" in c)), None)
        inn_col = next((c for c in df.columns if "international_non_proprietary" in c or c.startswith("active_substance")), None)
        df["parent_id"] = [matcher.parent_for(str(h), region="global") if holder_col and isinstance(h, str) else None
                           for h in (df[holder_col] if holder_col else [None] * len(df))]
        df["molecule_ids"] = [mids_for([str(x)]) if isinstance(x, str) else None for x in (df[inn_col] if inn_col else [None] * len(df))]
        df = df.astype(object).where(pd.notna(df), None)
        with db.writer() as w:
            w.execute("DROP TABLE IF EXISTS ema_medicines")
            w.register("_ema", df)
            w.execute("CREATE TABLE ema_medicines AS SELECT * FROM _ema")
            w.unregister("_ema")
        self.stats.rows_new = len(df)
        self.stats.notes.append(f"holder column: {holder_col}; INN column: {inn_col}; {len(keep)} columns")


NSE_TOPICS = [   # first match wins: the red-flag topics come first
    ("regulatory_action", r"action\(s\) (?:initiated|taken)|orders? passed|penalt|show[- ]cause|sebi order|adjudicat|"
                          r"search (?:and|&) seizure|income[- ]tax (?:search|survey|demand)|gst (?:demand|notice)|enforcement directorate"),
    ("litigation", r"litigation|dispute|arbitrat|insolvency|winding up|writ petition|lawsuit|class action|"
                   r"patent infringement|court|tribunal"),
    ("mgmt_exit", r"(?:resignation|cessation) of (?:the )?(?:statutory )?auditors?|"
                  r"(?:resignation|cessation) of [^.]{0,70}? as [^.]{0,45}?(?:director|cfo|chief|company secretary|"
                  r"compliance officer|managing|whole[- ]time|senior management|key managerial|ceo)"),
    ("credit", r"credit rating"),
    ("usfda", r"usfda|u\.s\. fda|us fda|form 483|warning letter|import alert|establishment inspection|eir\b|observations"),
    ("approval", r"approval|approved|launch|anda|tentative|nda\b|cdsco|dcgi"),
    ("results", r"financial results|quarter|q[1-4]\s*fy|earnings|investor|analyst|con\. call|press release.*results"),
    ("deal", r"acqui|merger|amalgamation|scheme of arrangement|divest|stake|joint venture|licens|agreement"),
    ("plant", r"plant|facility|unit|manufacturing site|fire|shutdown"),
    ("governance", r"board|director|auditor|resignation|appointment|agm|dividend|record date"),
]


TOPICS_VERSION = "nse_topics|v2"


class NseFilings(Connector):
    name = "nse_filings"
    title = "NSE Corporate Announcements (pharma)"
    agency = "NSE"
    schedule = {"trigger": "cron", "hour": "9-18", "minute": 50}
    description = "Corporate filings of every listed pharma group: results, USFDA disclosures, approvals, M&A, plant events."

    def retag(self):
        """Re-classify stored filings once whenever the topic rules change (in bulk: one UPDATE from a frame)."""
        import pandas as pd
        cur = db.cursor()
        if cur.execute("SELECT 1 FROM connector_state WHERE key = ?", [TOPICS_VERSION]).fetchone():
            return
        rows = cur.execute("SELECT seq_id, coalesce(category, '') || ' ' || coalesce(text, '') FROM corp_announcements").fetchall()
        df = pd.DataFrame([{"seq_id": sid, "topic": next((t for t, rx in NSE_TOPICS if re.search(rx, txt, re.I)), "other")}
                           for sid, txt in rows])
        with db.writer() as w:
            if len(df):
                w.register("_t", df)
                w.execute("UPDATE corp_announcements SET topic = _t.topic FROM _t WHERE corp_announcements.seq_id = _t.seq_id")
                w.unregister("_t")
            w.execute("INSERT OR REPLACE INTO connector_state VALUES (?, ?)", [TOPICS_VERSION, datetime.now().isoformat()])
        self.stats.notes.append(f"re-tagged {len(df):,} stored filings")

    def run(self):
        import httpx
        s = httpx.Client(headers={"User-Agent": BROWSER_UA, "Accept": "application/json", "Referer": "https://www.nseindia.com/"},
                         timeout=40, follow_redirects=True)
        s.get("https://www.nseindia.com/")
        tick = db.cursor().execute("SELECT id, ticker, name FROM parents WHERE ticker IS NOT NULL").fetchall()
        self.retag()
        with db.writer() as w:
            for pid, sym, pname in tick:
                try:
                    r = s.get("https://www.nseindia.com/api/corporate-announcements", params={"index": "equities", "symbol": sym})
                    items = r.json() if r.status_code == 200 else []
                except Exception:  # noqa: BLE001
                    items = []
                for a in items:
                    self.stats.rows_seen += 1
                    sid = str(a.get("seq_id") or "")
                    if not sid or w.execute("SELECT 1 FROM corp_announcements WHERE seq_id = ?", [sid]).fetchone():
                        continue
                    text = f"{a.get('desc') or ''} {a.get('attchmntText') or ''}"
                    topic = next((t for t, rx in NSE_TOPICS if re.search(rx, text, re.I)), "other")
                    try:
                        ts = datetime.strptime(a.get("an_dt") or "", "%d-%b-%Y %H:%M:%S")
                    except ValueError:
                        ts = None
                    w.execute("INSERT INTO corp_announcements VALUES (?,?,?,?,?,?,?,?, now())",
                              [sid, sym, pid, ts, a.get("desc"), a.get("attchmntText"), a.get("attchmntFile"), topic])
                    self.stats.rows_new += 1
                    if ts and (datetime.now() - ts).days <= 3 and topic in ("usfda", "approval", "deal", "plant", "results",
                                                                              "regulatory_action", "litigation", "mgmt_exit", "credit"):
                        sev = "high" if topic in ("usfda", "plant", "regulatory_action", "litigation", "mgmt_exit") else "medium"
                        self.emit(w, kind="filing", severity=sev, ts=ts, title=f"{pname} filing ({topic}): {(a.get('attchmntText') or a.get('desc') or '')[:180]}",
                                  url=a.get("attchmntFile"), entity_type="parent", entity_id=pid, dedupe_key=f"nse|{sid}")
