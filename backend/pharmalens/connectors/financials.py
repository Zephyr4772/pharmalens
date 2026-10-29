"""Quarterly results and results dates of listed pharma groups, from NSE.

Since 2025 SEBI's "Integrated Filing (Financials)" carries every listed company's quarterly results; NSE publishes
each as a structured page (one table: revenue, expenses by type, profit before / after tax, profit attributable to
owners, EPS, for the quarter and year to date). Each filing is parsed once into `fin_results` (₹ crore). NSE's
board-meeting list gives upcoming results dates (`results_calendar`). New results become events with year-on-year
change; a board meeting in the next week becomes a "results due" event.
"""
import re
import time
from datetime import date, datetime, timedelta

from selectolax.lexbor import LexborHTMLParser

from .. import db
from .base import BROWSER_UA, Connector

NSE = "https://www.nseindia.com/api/"
TO_CRORE = {"lakhs": 0.01, "lakh": 0.01, "crores": 1.0, "crore": 1.0, "millions": 0.1, "million": 0.1,
            "thousands": 0.0001, "rupees": 1e-7}
ROWS = {   # first matching label wins
    "revenue": r"^revenue from operations$",
    "other_income": r"^other income$",
    "total_income": r"^total income$",
    "total_expenses": r"^total expenses$",
    "employee_cost": r"^employee benefit expense",
    "finance_costs": r"^finance costs",
    "depreciation": r"^depreciation",
    "pbt": r"^total profit before tax",
    "tax": r"^total tax expenses",
    "net_profit": r"^total profit \(loss\) for period",
    "profit_owners": r"^profit or loss, attributable to owners of parent",
    "eps": r"^basic earnings \(loss\) per share from continuing and dis",
}


def _num(s: str) -> float | None:
    s = (s or "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[(),\s]", "", s)
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def _date(s: str) -> date | None:
    for fmt in ("%d-%m-%Y", "%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None


def parse_filing(html: str) -> list[dict]:
    """One row per reporting-period column of the profit-and-loss table, amounts in ₹ crore."""
    doc = LexborHTMLParser(html)
    tables = doc.css("table")
    unit = None
    for tr in tables[0].css("tr") if tables else []:
        cells = [re.sub(r"\s+", " ", c.text()).strip() for c in tr.css("td,th")]
        if len(cells) < 2:
            continue
        label, val = cells[0].lower(), cells[1].lower()
        if label.startswith("level of rounding"):
            unit = TO_CRORE.get(val.strip(), unit)
        elif label.startswith("description of presentation currency") and unit is None:
            # 2025 filings carry no rounding row and say "INR (in Actuals)": plain rupees
            unit = 1e-7 if "actual" in val else next((v for k, v in TO_CRORE.items() if k in val), None)
    unit = unit or 1.0
    pnl = next((t for t in tables if re.search(r"revenue from operations", t.text(), re.I)
                and re.search(r"date of start of reporting period", t.text(), re.I)), None)
    if pnl is None:
        return []
    rows = [[re.sub(r"\s+", " ", c.text()).strip() for c in tr.css("td,th")] for tr in pnl.css("tr")]
    starts = ends = None
    meta = {}
    values: dict[str, list] = {}
    for r in rows:
        if len(r) < 3:
            continue
        label, vals = r[1].lower(), r[2:]
        if label.startswith("date of start of reporting period"):
            starts = [_date(v) for v in vals]
        elif label.startswith("date of end of reporting period"):
            ends = [_date(v) for v in vals]
        elif label.startswith("whether results are audited"):
            meta["audited"] = vals
        elif label.startswith("nature of report"):
            meta["nature"] = vals
        else:
            for field, rx in ROWS.items():
                if field not in values and re.search(rx, label):
                    values[field] = [_num(v) for v in vals]
    if not starts or not ends:
        return []
    out = []
    for i, (s, e) in enumerate(zip(starts, ends)):
        if not s or not e:
            continue
        row = {"period_start": s, "period_end": e,
               "audited": (meta.get("audited") or [None] * 9)[i] if i < len(meta.get("audited") or []) else None,
               "consolidated": "consolidated" in ((meta.get("nature") or [""] * 9)[i] or "").lower() if meta.get("nature") else None}
        for field, vals in values.items():
            v = vals[i] if i < len(vals) else None
            row[field] = v if field == "eps" or v is None else round(v * unit, 4)
        # guard: no Indian pharma group books ₹5 lakh crore in a quarter; such a figure is an undeclared rupee unit
        if (row.get("revenue") or 0) > 500_000:
            for field in values:
                if field != "eps" and row.get(field) is not None:
                    row[field] = round(row[field] * 1e-7, 4)
        out.append(row)
    return out


class NseResults(Connector):
    name = "nse_results"
    title = "NSE Quarterly Results & Results Dates (pharma)"
    agency = "NSE"
    schedule = {"trigger": "cron", "hour": "10-22/2", "minute": 20}
    description = ("Quarterly results of every listed pharma group (NSE integrated filing: revenue, costs, profit, EPS) "
                   "and announced board-meeting dates for results.")

    def run(self):
        import httpx
        s = httpx.Client(headers={"User-Agent": BROWSER_UA, "Accept": "application/json", "Referer": "https://www.nseindia.com/"},
                         timeout=60, follow_redirects=True)
        s.get("https://www.nseindia.com/")
        cur = db.cursor()
        groups = cur.execute("SELECT id, ticker, name FROM parents WHERE ticker IS NOT NULL ORDER BY ticker").fetchall()
        done = {r[0] for r in cur.execute("SELECT key FROM connector_state WHERE key LIKE 'finres|%'").fetchall()}
        parsed = meetings = 0
        for pid, sym, gname in groups:
            # ---- results filings
            try:
                lst = s.get(NSE + "integrated-filing-results",
                            params={"index": "equities", "symbol": sym, "type": "Integrated Filing- Financials"}).json().get("data") or []
            except Exception as e:  # noqa: BLE001 — one symbol must not stop the rest
                self.stats.notes.append(f"{sym}: {str(e)[:60]}")
                lst = []
            for f in lst:
                key = f"finres|{f.get('seq_Id')}|{f.get('consolidated')}"
                if key in done or not f.get("ixbrl"):
                    continue
                try:
                    rows = parse_filing(s.get(f["ixbrl"]).text)
                except Exception as e:  # noqa: BLE001
                    self.stats.notes.append(f"{sym} {f.get('qe_Date')}: {str(e)[:60]}")
                    continue
                time.sleep(0.4)
                filed = None
                try:
                    filed = datetime.strptime(f.get("broadcast_Date") or "", "%d-%b-%Y %H:%M:%S")
                except ValueError:
                    pass
                cons = (f.get("consolidated") or "").lower().startswith("consol")
                with db.writer() as w:
                    for r in rows:
                        w.execute("""INSERT OR REPLACE INTO fin_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, now())""",
                                  [sym, pid, r["period_start"], r["period_end"], cons if r["consolidated"] is None else r["consolidated"],
                                   r.get("audited"), r.get("revenue"), r.get("other_income"), r.get("total_income"),
                                   r.get("total_expenses"), r.get("employee_cost"), r.get("finance_costs"), r.get("depreciation"),
                                   r.get("pbt"), r.get("tax"), r.get("net_profit"), r.get("profit_owners"), r.get("eps"),
                                   filed, f["ixbrl"]])
                        self.stats.rows_new += 1
                    w.execute("INSERT OR REPLACE INTO connector_state VALUES (?, ?)", [key, datetime.now().isoformat()])
                    if cons and filed and (datetime.now() - filed).days <= 3:
                        self._announce(w, pid, sym, gname, rows, f)
                parsed += 1
            # ---- board meetings (results dates)
            try:
                bms = s.get(NSE + "corporate-board-meetings", params={"index": "equities", "symbol": sym}).json() or []
            except Exception:  # noqa: BLE001
                bms = []
            with db.writer() as w:
                for b in bms if isinstance(bms, list) else []:
                    md = _date(b.get("bm_date") or "")
                    if not md:
                        continue
                    try:
                        ann = datetime.strptime(b.get("bm_timestamp") or "", "%d-%b-%Y %H:%M:%S")
                    except ValueError:
                        ann = None
                    w.execute("INSERT OR REPLACE INTO results_calendar VALUES (?,?,?,?,?,?)",
                              [sym, pid, md, b.get("bm_purpose"), (b.get("bm_desc") or "")[:600], ann])
                    meetings += 1
                    if date.today() <= md <= date.today() + timedelta(days=7) and re.search(r"result", b.get("bm_desc") or "", re.I):
                        self.emit(w, kind="results_due", severity="info", ts=ann or datetime.now(),
                                  title=f"{gname}: board meets {md:%d %b} to approve results", entity_type="parent", entity_id=pid,
                                  dedupe_key=f"resdue|{sym}|{md}")
            time.sleep(0.4)
        self.stats.rows_seen = parsed
        self.stats.notes.append(f"{parsed} new filings parsed, {meetings} board meetings seen for {len(groups)} listed groups")

    def _announce(self, w, pid: int, sym: str, gname: str, rows: list[dict], f: dict):
        q = next((r for r in rows if r.get("revenue") is not None and (r["period_end"] - r["period_start"]).days < 100), None)
        if not q:
            return
        # the same quarter a year earlier
        prev = w.execute("""SELECT revenue, net_profit FROM fin_results WHERE symbol = ? AND consolidated
                            AND period_end BETWEEN ? AND ? AND date_diff('day', period_start, period_end) < 100""",
                         [sym, q["period_end"] - timedelta(days=375), q["period_end"] - timedelta(days=355)]).fetchone()

        def chg(new, old):
            return f" ({(new / old - 1) * 100:+.0f}% YoY)" if new is not None and old else ""
        rev_chg = (q["revenue"] / prev[0] - 1) if prev and prev[0] and q.get("revenue") else None
        prof_chg = (q["net_profit"] / prev[1] - 1) if prev and prev[1] and q.get("net_profit") and prev[1] > 0 else None
        sev = "high" if (prof_chg is not None and abs(prof_chg) >= 0.25) or (q.get("net_profit") or 0) < 0 else "medium"
        label = f"Q{((q['period_end'].month - 4) % 12) // 3 + 1} FY{(q['period_end'].year + (1 if q['period_end'].month > 3 else 0)) % 100:02d}"
        self.emit(w, kind="results", severity=sev, ts=datetime.now(),
                  title=f"{gname} {label} results: revenue ₹{q['revenue']:,.0f} cr{chg(q['revenue'], prev[0] if prev else None)}, "
                        f"net profit ₹{(q.get('net_profit') or 0):,.0f} cr{chg(q.get('net_profit'), prev[1] if prev else None)}",
                  url=f.get("ixbrl"), entity_type="parent", entity_id=pid, dedupe_key=f"results|{sym}|{q['period_end']}",
                  payload={"revenue_yoy": rev_chg, "profit_yoy": prof_chg})
