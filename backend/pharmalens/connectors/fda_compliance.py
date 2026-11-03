"""US FDA compliance actions (warning letters, injunctions, seizures) and import refusals (FDA Data Dashboard).

Same API and key as fda_inspections (FDA_DD_USER / FDA_DD_KEY). Compliance actions: every drug action, any country (a
few thousand; abroad they only reach sites our India-facing sources list). Import refusals: drug and biologic shipments
from India (the API has no drug-only filter for refusals; ProductCategory "Drugs and Biologics" is the closest).
Refusal charges are FDA charge codes (e.g. 75 = unapproved new drug), kept as given. New warning letters to Indian
firms raise events; refusals do not (thousands a year, mostly small shippers). Licence: US government data (open).
"""
import os
import re
from datetime import datetime

import pandas as pd

from .. import db
from .fda_inspections import FdaInspections, is_drug

DDL = """
CREATE TABLE IF NOT EXISTS fda_compliance_actions (
    case_id VARCHAR PRIMARY KEY, fei VARCHAR, firm VARCHAR, address VARCHAR, city VARCHAR, state VARCHAR, zip VARCHAR, country VARCHAR,
    region VARCHAR, center VARCHAR, action_type VARCHAR, action_date DATE, fiscal_year VARCHAR, fetched_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS fda_import_refusals (
    shipment_id VARCHAR, fei VARCHAR, firm VARCHAR, address VARCHAR, city VARCHAR, country VARCHAR, product_code VARCHAR,
    product VARCHAR, industry VARCHAR, refusal_date DATE, charges VARCHAR, fda_sample VARCHAR, fetched_at TIMESTAMP
);
"""
ACT = {"case_id": "CaseInjunctionID", "fei": "FEINumber", "firm": "LegalName", "address": "AddressLine1", "city": "City", "state": "State",
       "zip": "ZipCode", "country": "CountryName", "region": "Region", "center": "Center", "action_type": "ActionType",
       "action_date": "ActionTakenDate", "fiscal_year": "FiscalYear"}
REF = {"shipment_id": "ShipmentID", "fei": "FEINumber", "firm": "FirmName", "address": "AddressLine1", "city": "City", "country": "CountryName",
       "product_code": "ProductCode", "product": "ProductCodeDescription", "industry": "IndustryCodeDescription",
       "refusal_date": "RefusalDate", "charges": "RefusalCharges", "fda_sample": "FDASampleAnalysis"}


def pick(df: pd.DataFrame, cols: dict, date_col: str) -> pd.DataFrame:
    out = pd.DataFrame({k: (df[v] if v in df else None) for k, v in cols.items()})
    for c in out.columns:
        if c != date_col:
            out[c] = out[c].map(lambda v: None if v is None or pd.isna(v) else str(v).strip() or None)
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce").dt.date
    return out.astype(object).where(pd.notna(out), None)


class FdaCompliance(FdaInspections):
    name = "fda_compliance"
    title = "US FDA warning letters and import refusals"
    agency = "US FDA (Data Dashboard)"
    schedule = {"trigger": "cron", "day_of_week": "tue", "hour": 6, "minute": 55}
    description = "Drug compliance actions (warning letters, injunctions) and refused drug shipments from India, by FEI and address."

    def run(self):
        with db.writer() as w:
            w.execute(DDL)
        if not (os.getenv("FDA_DD_USER") and os.getenv("FDA_DD_KEY")):
            self.stats.notes.append("no data: set FDA_DD_USER / FDA_DD_KEY")
            return
        a = pick(self._api("compliance_actions", {"ProductType": ["Drugs"]}, "CaseInjunctionID"), ACT, "action_date")
        a = a[a["case_id"].notna()].drop_duplicates("case_id")
        r = pick(self._api("import_refusals", {"CountryName": ["India"], "ProductCategory": ["Drugs and Biologics"]}, "ShipmentID"), REF,
                 "refusal_date")
        r = r[r["industry"].map(is_drug) | r["industry"].isna()].drop_duplicates(["shipment_id", "product_code"])
        self.stats.rows_seen = len(a) + len(r)
        now = datetime.now()
        a["fetched_at"], r["fetched_at"] = now, now
        with db.writer() as w:
            old = {x[0] for x in w.execute("SELECT case_id FROM fda_compliance_actions").fetchall()}
            for table, df in (("fda_compliance_actions", a), ("fda_import_refusals", r)):
                cols = ", ".join(df.columns)
                w.execute(f"DELETE FROM {table}").fetchall()
                w.register("_d", df)
                w.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _d").fetchall()
                w.unregister("_d")
            new = a[~a["case_id"].isin(old)]
            self.stats.rows_new = len(new)
            if old:      # the first load is the baseline: no events for history
                for x in new.itertuples():
                    if re.search(r"india", str(x.country or ""), re.I):
                        if self.emit(w, kind="usfda", severity="high", ts=x.action_date,
                                     title=f"US FDA {x.action_type or 'compliance action'}: {x.firm} ({x.city})",
                                     dedupe_key=f"fdaca|{x.case_id}", payload={"fei": x.fei, "action_type": x.action_type}):
                            self.stats.events_new += 1
        self.stats.notes.append(f"{len(a):,} drug compliance actions ({(a['country'] == 'India').sum():,} India), "
                                f"{len(r):,} refused drug shipments from India")
