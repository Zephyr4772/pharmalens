"""Foreign-regulator signals relevant to Indian manufacturers (openFDA)."""
from datetime import date, datetime, timedelta

from .. import db, matcher
from ..config import OPENFDA_API_KEY
from .base import Connector


def ymd(s: str | None) -> date | None:
    try:
        return datetime.strptime(s, "%Y%m%d").date() if s else None
    except ValueError:
        return None


class OpenFdaIndiaRecalls(Connector):
    name = "openfda_recalls"
    title = "US FDA Recalls of India-made Drugs"
    agency = "US FDA (openFDA)"
    schedule = {"trigger": "cron", "hour": 7, "minute": 20}
    description = "Drug recall enforcement reports where the recalling firm is in India (class I/II/III)."

    def run(self):
        have = db.cursor().execute("SELECT count(*) FROM usfda_actions WHERE kind = 'recall'").fetchone()[0]
        since = (date.today() - timedelta(days=60 if have else 365 * 3)).strftime("%Y%m%d")
        skip, page = 0, 100
        while True:
            params = {"search": f'country:"India" AND report_date:[{since} TO 29991231]', "limit": page, "skip": skip,
                      "sort": "report_date:desc"}
            if OPENFDA_API_KEY:
                params["api_key"] = OPENFDA_API_KEY
            r = self.get("https://api.fda.gov/drug/enforcement.json", params=params)
            if r.status_code == 404:
                break
            r.raise_for_status()
            res = r.json().get("results", [])
            if not res:
                break
            with db.writer() as cur:
                for x in res:
                    rid = f"recall-{x.get('recall_number')}"
                    self.stats.rows_seen += 1
                    if cur.execute("SELECT 1 FROM usfda_actions WHERE id = ?", [rid]).fetchone():
                        continue
                    firm = x.get("recalling_firm")
                    pid = matcher.parent_for(firm, region="global")
                    issued = ymd(x.get("report_date"))
                    subject = f"{x.get('classification')}: {x.get('product_description', '')[:300]} — {x.get('reason_for_recall', '')[:300]}"
                    cur.execute("INSERT INTO usfda_actions VALUES (?,?,?,?,?,?,?,?, now())",
                                [rid, "recall", firm, "India", subject, issued, None, pid])
                    self.stats.rows_new += 1
                    sev = "critical" if x.get("classification") == "Class I" else ("high" if pid else "medium")
                    self.emit(cur, kind="recall", severity=sev, ts=issued,
                              title=f"USFDA {x.get('classification')} recall — {firm}: {x.get('product_description', '')[:120]}",
                              body=x.get("reason_for_recall"), entity_type="parent" if pid else None, entity_id=pid,
                              dedupe_key=f"fda|{rid}", payload={"status": x.get("status"), "city": x.get("city")})
            if len(res) < page or skip > 2000:
                break
            skip += page
