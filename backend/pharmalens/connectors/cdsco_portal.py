"""CDSCO online portal (cdscoonline.gov.in) — structured JSON behind the public pages.

* cdsco_nsq_portal   — every NSQ / spurious batch, central + state labs, 2019 → latest month.
                       Source of truth for the months it covers: PDF-parsed and mirrored rows
                       for those months are replaced.
* cdsco_approvals_db — every approval (new drug, SND, FDC, biological, IND, vet) with composition,
                       dosage form, indication, applicant and all manufacturing sites, 2018 → today.
* cdsco_brands       — Rule 84AB brand-name registry: brand → licensed manufacturer, licence no.,
                       generic. Enumerated with two-letter searches (the endpoint is search-only).

Every raw response is archived under data/raw/<connector>/ before parsing.
"""
import itertools
import json
import re
import string
import time
from datetime import date, datetime

from .. import db, matcher
from ..normalize import fix_mojibake, norm
from .base import BROWSER_UA, Connector

PORTAL = "https://cdscoonline.gov.in/CDSCO/"
DIVISIONS = {1: "biological", 8: "subsequent_new_drug", 9: "new_drug", 10: "fdc", 12: "ind", 24: "veterinary"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class _Portal(Connector):
    agency = "CDSCO"
    referer = PORTAL + "homepage"

    def j(self, path: str, **params):
        """GET a portal endpoint; the portal sometimes returns JSON encoded inside a JSON string."""
        for attempt in range(3):
            r = self.http.get(PORTAL + path, params=params,
                              headers={"X-Requested-With": "XMLHttpRequest", "Referer": self.referer, "User-Agent": BROWSER_UA})
            if r.status_code == 200:
                try:
                    d = r.json()
                except ValueError:
                    d = json.loads(r.text)
                return json.loads(d) if isinstance(d, str) else d
            time.sleep(3 * (attempt + 1))
        raise RuntimeError(f"{path} {params} -> HTTP {r.status_code}")


def month_key(mon_year: str | None) -> str | None:
    """'AUG-2026' / 'Aug-2026' -> '2026-08'."""
    if not mon_year:
        return None
    m = re.match(r"([A-Za-z]{3})[A-Za-z]*[-\s](\d{4})", mon_year.strip())
    if not m:
        return None
    return f"{m.group(2)}-{MONTHS.index(m.group(1).title()) + 1:02d}"


# ------------------------------------------------------------------ NSQ / spurious
class CdscoNsqPortal(_Portal):
    name = "cdsco_nsq_portal"
    title = "CDSCO NSQ & Spurious Portal (official)"
    schedule = {"trigger": "cron", "hour": "9,16", "minute": 20}
    description = "Official structured NSQ and spurious batch data from CDSCO's public portal, central and state labs, 2019 onward."
    referer = PORTAL + "viewPublicNSQDrug"
    refresh_recent = 3   # months re-read every run (late additions are common)

    def run(self):
        self.http.get(self.referer)   # session cookie
        cur = db.cursor()
        done = {r[0] for r in cur.execute("SELECT key FROM connector_state WHERE key LIKE 'nsqportal|%'").fetchall()}
        for tab, endpoint, category in (("nsq", "filteredNsqDrugTable", "NSQ"), ("spurious", "filteredSpuriousDrugTable", "SPURIOUS")):
            months = []
            for y in self.j("reportingYears", tab=tab):
                for m in self.j("publicReportingMonths", year=y, tab=tab):
                    months.append(f"{m}-{y}")
            months.sort(key=lambda s: month_key(s) or "")
            recent = set(months[-self.refresh_recent:])
            for mon in months:
                if f"nsqportal|{tab}|{mon}" in done and mon not in recent:
                    continue
                d = self.j(endpoint, month=mon, source="All", tab=tab)
                self.archive(json.dumps(d, ensure_ascii=False), "json", key=f"{tab}-{mon}")
                rows = d.get("aaData") or []
                self.stats.rows_seen += len(rows)
                self.ingest(rows, category, mon)
                with db.writer() as w:
                    w.execute("INSERT OR REPLACE INTO connector_state VALUES (?, ?)", [f"nsqportal|{tab}|{mon}", datetime.now().isoformat()])

    def ingest(self, rows: list[dict], category: str, mon: str):
        mk = month_key(mon)
        url = f"{PORTAL}viewPublicNSQDrug#{category.lower()}/{mon}"
        with db.writer() as w:
            if rows:
                # the portal is authoritative for this month: drop PDF-parsed / mirrored rows it supersedes
                w.execute("""DELETE FROM reg_nsq WHERE alert_month = ? AND category = ?
                             AND (source_url IS NULL OR source_url NOT LIKE ?)""", [mk, category, PORTAL + "%"])
            for r in rows:
                product = fix_mojibake((r.get("str_product_name") or "").strip())
                batch = (r.get("str_batch_no") or "").strip()
                mfr = fix_mojibake((r.get("str_manufactured_by") or "").strip())
                key = norm(f"portal|{category}|{product}|{batch}|{mfr[:60]}|{mk}")
                if w.execute("SELECT 1 FROM reg_nsq WHERE dedupe_key = ?", [key]).fetchone():
                    continue
                cid = matcher.company_for(mfr)
                mids = matcher.molecules_in(product)
                w.execute("""INSERT INTO reg_nsq (alert_month, category, product_text, batch_no, mfg_date, exp_date, manufacturer, reason,
                             drawn_by, lab, source_url, company_id, molecule_ids, dedupe_key, fetched_at)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, now())""",
                          [month_key(r.get("dt_reporting_month_year")) or mk, category, product, batch,
                           r.get("dt_manufacturing_date"), r.get("dt_expiry_date"), mfr,
                           fix_mojibake(r.get("str_nsq_result") or r.get("str_reason") or ""),
                           r.get("str_reporting_source"), r.get("str_reported_by_lab_or_state"), url, cid,
                           ",".join(map(str, mids)) or None, key])
                self.stats.rows_new += 1
                parent = w.execute("SELECT parent_id FROM companies WHERE id = ?", [cid]).fetchone()[0] if cid else None
                recent = bool(mk) and mk >= f"{date.today().year - 1}-{date.today().month:02d}"   # last 12 months
                if recent and (category == "SPURIOUS" or parent):
                    self.emit(w, kind="spurious" if category == "SPURIOUS" else "nsq",
                              severity="critical" if category == "SPURIOUS" else "high",
                              title=f"{category}: {product} batch {batch}", body=f"{mfr} — {r.get('str_nsq_result') or ''}",
                              url=url, entity_type="company" if cid else None, entity_id=cid,
                              dedupe_key=f"nsqportal|{key}", payload={"month": mk, "molecule_ids": mids})


# ------------------------------------------------------------------ approvals DB
class CdscoApprovalsDb(_Portal):
    name = "cdsco_approvals_db"
    title = "CDSCO Approvals Database (official)"
    schedule = {"trigger": "cron", "hour": "10,19", "minute": 5}
    description = "Every CDSCO approval since 2018 with composition, dosage form, indication, applicant and manufacturing sites."
    referer = PORTAL + "cdscoDrugs"

    def run(self):
        from ..derived import migrate
        migrate()
        self.http.get(self.referer)
        cur = db.cursor()
        have = {r[0] for r in cur.execute("SELECT key FROM connector_state WHERE key LIKE 'approvalsdb|%'").fetchall()}
        today = date.today()
        for y in self.j("getApprovalYears"):
            months = self.j("getApprovalMonths", year=y)
            for m in months:
                current = int(y) == today.year and MONTHS.index(m) + 1 >= today.month - 1
                if f"approvalsdb|{y}|{m}" in have and not current:
                    continue
                d = self.j("loadDrugApprovals", searchText="", year=y, month=m, drugTypeValue="")
                self.archive(json.dumps(d, ensure_ascii=False), "json", key=f"{y}-{m}")
                rows = d.get("aaData") or []
                self.stats.rows_seen += len(rows)
                self.ingest(rows)
                with db.writer() as w:
                    w.execute("INSERT OR REPLACE INTO connector_state VALUES (?, ?)", [f"approvalsdb|{y}|{m}", datetime.now().isoformat()])

    def ingest(self, rows: list[dict]):
        with db.writer() as w:
            for r in rows:
                fid = r.get("num_form_id")
                key = f"cdscodb|{fid}|{norm(r.get('str_drug_name') or '')[:80]}|{r.get('dt_closure_dt')}"
                if w.execute("SELECT 1 FROM reg_approvals WHERE dedupe_key = ?", [key]).fetchone():
                    continue
                try:
                    when = datetime.strptime(r.get("dt_closure_dt") or "", "%d-%b-%Y").date()
                except ValueError:
                    when = None
                drug = fix_mojibake((r.get("str_drug_name") or "").strip())
                comp = fix_mojibake((r.get("str_composition") or "").strip())
                division = DIVISIONS.get(r.get("num_division_id"), str(r.get("num_division_id")))
                sites = [s.strip() for s in re.split(r"<br\s*/?>", r.get("manuf_addr") or "") if s.strip()]
                mids = matcher.molecules_in(f"{drug} {comp}", limit=8)
                applicant = fix_mojibake((r.get("str_man_unit_name") or "").strip())
                w.execute("""INSERT INTO reg_approvals (agency, drug_text, indication, approved_on, applicant, approval_type, source_url,
                             molecule_ids, dedupe_key, fetched_at, composition, dosage_form, sites, division, applied_for, form_id)
                             VALUES ('CDSCO',?,?,?,?,?,?,?,?, now(),?,?,?,?,?,?)""",
                          [drug, fix_mojibake(r.get("str_indication") or "") or None, when, applicant, division,
                           PORTAL + "cdscoDrugs", ",".join(map(str, mids)) or None, key, comp or None,
                           r.get("str_dosage"), json.dumps(sites, ensure_ascii=False) if sites else None, division,
                           r.get("str_applied_for"), fid])
                self.stats.rows_new += 1
                if when and (date.today() - when).days <= 45:
                    pid = matcher.parent_for(applicant)
                    self.emit(w, kind="approval", severity="medium", ts=when,
                              title=f"CDSCO approval ({division.replace('_', ' ')}): {drug[:120]} — {applicant[:60]}",
                              body=(r.get("str_indication") or "")[:500], url=PORTAL + "cdscoDrugs",
                              entity_type="parent" if pid else None, entity_id=pid, dedupe_key=f"appr|{key}",
                              payload={"molecule_ids": mids, "dosage": r.get("str_dosage")})


# ------------------------------------------------------------------ Rule 84AB brand registry
class CdscoBrandRegistry(_Portal):
    name = "cdsco_brands"
    title = "CDSCO Brand Name Registry (Rule 84AB)"
    schedule = {"trigger": "cron", "day_of_week": "sun", "hour": 3, "minute": 0}
    description = "Every brand registered under Rule 84AB with its licensed manufacturer, licence number and generic name."
    referer = PORTAL + "brandNames"

    def run(self):
        self.http.get(self.referer)
        seen: dict[tuple, dict] = {}
        letters = string.ascii_lowercase + string.digits
        for a, b in itertools.product(string.ascii_lowercase, letters):
            q = a + b
            d = self.j("loadRule84abBrandNames", searchText=q)
            rows = d.get("aaData") or []
            for r in rows:
                k = (norm(r.get("firm_name")), (r.get("license_number") or "").strip(), norm(r.get("brand_name")))
                seen[k] = r
            time.sleep(0.15)
        self.archive(json.dumps(list(seen.values()), ensure_ascii=False), "json", key=f"brands-{date.today():%Y%m%d}")
        self.stats.rows_seen = len(seen)
        with db.writer() as w:
            before = w.execute("SELECT count(*) FROM brand_registry").fetchone()[0]
            w.execute("DELETE FROM brand_registry")
            for r in seen.values():
                firm = fix_mojibake((r.get("firm_name") or "").strip())
                brand = fix_mojibake((r.get("brand_name") or "").strip())
                generic = fix_mojibake((r.get("generic_name") or "").strip())
                if generic in ("-", ""):
                    generic = None
                w.execute("INSERT INTO brand_registry VALUES (?,?,?,?,?,?, now())",
                          [firm, (r.get("license_number") or "").strip() or None, generic, brand, norm(brand),
                           matcher.company_for(firm)])
            self.stats.rows_new = max(0, len(seen) - before)
