"""US FDA inspections and their Form 483 citations (FDA Data Dashboard), for drug sites.

Two sanctioned ways in, whichever is available:
  * API: set FDA_DD_USER (the e-mail registered with FDA's OII Unified Logon) and FDA_DD_KEY (the key FDA mails) in
    the server's .env; the feed pages through the inspections_classifications and inspections_citations endpoints.
  * Files: download "Entire Inspections Dataset" and "Entire Citations Dataset" from
    https://datadashboard.fda.gov/oii/cd/inspections.htm and put the two .xlsx files in data/raw/fda_dashboard/;
    the newest of each is loaded.
No scraping of the dashboard itself. Column names are matched loosely (the API and the exports name them
differently). Only drug inspections are kept. New Official Action Indicated (OAI) inspections of Indian firms raise
events. Licence: US government data (open).
"""
import json
import os
import re
from datetime import date, datetime

import pandas as pd

from .. import db
from ..config import RAW_DIR
from .base import Connector

API = "https://api-datadashboard.fda.gov/v1/{}"
DROP = RAW_DIR / "fda_dashboard"

# loose column names -> ours
ALIASES = {
    "inspection_id": ["inspectionid"], "fei": ["feinumber", "fei"], "firm": ["legalname", "firmname", "firm"],
    "city": ["city", "cityname"], "state": ["state", "statecode", "statename", "inspectionstate"], "zip": ["zip", "zipcode", "postalcode"],
    "country": ["countryarea", "country", "countryname", "countrycode"], "end_date": ["inspectionenddate", "enddate"],
    "classification": ["classification", "inspectionclassification"], "product_type": ["producttype"], "project_area": ["projectarea", "programarea"],
    "posted_citations": ["postedcitations"], "fiscal_year": ["fiscalyear"], "district": ["district"],
    "act_cfr": ["actcfrnumber", "cfrnumber", "actcfr"], "short_desc": ["shortdescription"], "long_desc": ["longdescription"],
}
INSP_COLS = ["inspection_id", "fei", "firm", "city", "state", "zip", "country", "end_date", "classification", "product_type", "project_area",
             "posted_citations", "fiscal_year", "district"]
CIT_COLS = ["inspection_id", "fei", "firm", "end_date", "project_area", "act_cfr", "short_desc", "long_desc"]

DDL = """
CREATE TABLE IF NOT EXISTS fda_inspections (
    inspection_id VARCHAR PRIMARY KEY, fei VARCHAR, firm VARCHAR, city VARCHAR, state VARCHAR, zip VARCHAR, country VARCHAR,
    end_date DATE, classification VARCHAR, product_type VARCHAR, project_area VARCHAR, posted_citations VARCHAR,
    fiscal_year VARCHAR, district VARCHAR, fetched_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS fda_citations (
    inspection_id VARCHAR, fei VARCHAR, firm VARCHAR, end_date DATE, project_area VARCHAR, act_cfr VARCHAR,
    short_desc VARCHAR, long_desc VARCHAR, fetched_at TIMESTAMP
);
"""


def normalise(df: pd.DataFrame, want: list[str]) -> pd.DataFrame:
    flat = {re.sub(r"[^a-z0-9]", "", str(c).lower()): c for c in df.columns}
    out = pd.DataFrame()
    for col in want:
        src = next((flat[a] for a in ALIASES[col] if a in flat), None)
        out[col] = df[src] if src is not None else None
    for col in ("inspection_id", "fei", "zip", "fiscal_year"):
        if col in out:
            out[col] = out[col].map(lambda v: None if pd.isna(v) else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v).strip()))
    out["end_date"] = pd.to_datetime(out["end_date"], errors="coerce").dt.date
    return out.astype(object).where(pd.notna(out), None)


def is_drug(v) -> bool:
    return bool(v) and bool(re.search(r"drug", str(v), re.I))


class FdaInspections(Connector):
    name = "fda_inspections"
    title = "US FDA inspections and 483 citations"
    agency = "US FDA (Data Dashboard)"
    schedule = {"trigger": "cron", "day_of_week": "tue", "hour": 6, "minute": 40}
    description = "Drug-site inspections (classification NAI / VAI / OAI) and Form 483 citations, by FEI and address."

    def _api(self, endpoint: str) -> pd.DataFrame:
        user, key = os.getenv("FDA_DD_USER"), os.getenv("FDA_DD_KEY")
        rows, start = [], 1
        with self.http() as s:
            while True:
                r = s.post(API.format(endpoint), headers={"Content-Type": "application/json", "Authorization-User": user, "Authorization-Key": key},
                           json={"start": start, "rows": 5000, "sort": "InspectionEndDate", "sortorder": "desc"}, timeout=180)
                if r.status_code == 412:
                    break
                r.raise_for_status()
                body = r.json()
                batch = body.get("result") or []
                rows += batch
                if len(batch) < 5000:
                    break
                start += len(batch)
        self.archive(json.dumps(rows[:50]).encode(), "json", key=f"{endpoint}-sample-{date.today():%Y%m%d}")
        return pd.DataFrame(rows)

    def _file(self, prefix: str) -> pd.DataFrame | None:
        files = sorted(DROP.glob(f"{prefix}*.xlsx"), key=lambda p: p.stat().st_mtime) if DROP.exists() else []
        if not files:
            return None
        self.stats.notes.append(f"loaded {files[-1].name}")
        return pd.read_excel(files[-1])

    def run(self):
        with db.writer() as w:
            w.execute(DDL)
        if os.getenv("FDA_DD_USER") and os.getenv("FDA_DD_KEY"):
            insp, cit, how = self._api("inspections_classifications"), self._api("inspections_citations"), "API"
        else:
            insp, cit, how = self._file("Inspections"), self._file("Citations"), "files"
        if insp is None or not len(insp):
            self.stats.notes.append("no data: set FDA_DD_USER / FDA_DD_KEY, or drop the dashboard's InspectionsDataset.xlsx and "
                                    f"CitationsDataset.xlsx into {DROP}")
            return
        i = normalise(insp, INSP_COLS)
        i = i[i["product_type"].map(is_drug) | i["product_type"].isna()]
        i = i[i["inspection_id"].notna()].drop_duplicates("inspection_id")
        c = normalise(cit, CIT_COLS) if cit is not None and len(cit) else pd.DataFrame(columns=CIT_COLS)
        c = c[c["inspection_id"].isin(set(i["inspection_id"]))]
        self.stats.rows_seen = len(i) + len(c)
        now = datetime.now()
        with db.writer() as w:
            old = {r[0] for r in w.execute("SELECT inspection_id FROM fda_inspections").fetchall()}
            i["fetched_at"], c["fetched_at"] = now, now
            w.execute("DELETE FROM fda_inspections").fetchall()
            w.register("_i", i)
            w.execute(f"INSERT INTO fda_inspections SELECT {', '.join(INSP_COLS)}, fetched_at FROM _i").fetchall()
            w.unregister("_i")
            w.execute("DELETE FROM fda_citations").fetchall()
            if len(c):
                w.register("_c", c)
                w.execute(f"INSERT INTO fda_citations SELECT {', '.join(CIT_COLS)}, fetched_at FROM _c").fetchall()
                w.unregister("_c")
            new = i[~i["inspection_id"].isin(old)]
            self.stats.rows_new = len(new)
            if old:      # the first load is the baseline: no events for history
                for r in new.itertuples():
                    if re.search(r"official action", str(r.classification or ""), re.I) and re.search(r"india", str(r.country or ""), re.I):
                        if self.emit(w, kind="usfda", severity="high", ts=r.end_date,
                                     title=f"US FDA inspection classified OAI: {r.firm} ({r.city}, {r.state})",
                                     dedupe_key=f"fdainsp|{r.inspection_id}", payload={"fei": r.fei, "classification": r.classification}):
                            self.stats.events_new += 1
        self.stats.notes.append(f"{how}: {len(i):,} drug inspections, {len(c):,} citations")
