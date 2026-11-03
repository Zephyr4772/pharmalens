"""Manufacturing site profiles (plant stage 2): the records at one plant of one firm."""
import json

from fastapi import APIRouter, HTTPException

from ... import db
from ...linking.store import HIGH
from ..common import cleanrows

router = APIRouter(prefix="/sites", tags=["sites"])

SITE_COLS = """s.site_key, s.maker_key, s.maker_name, s.kind, s.country, s.pin, s.state, s.locality, s.address, s.units, s.records, s.roles"""


def _recs(cur, table: str, cols: str, key_expr: str, sk: str, order: str, limit: int = 80) -> list[dict]:
    return db.rows(cur, f"""SELECT {cols}, l.method, l.confidence, l.confidence < {HIGH} AS inferred FROM entity_links l
                            JOIN {table} t ON {key_expr} = l.src_key
                            WHERE l.linker = 'site:records' AND l.src_table = '{table}' AND l.dst_id = ? ORDER BY {order} LIMIT {limit}""", [sk])


def summary(cur, where: str, args: list, limit: int = 60) -> list[dict]:
    """Sites with their record counts by kind (approvals, NSQ, US FDA, debarments), most records first."""
    try:
        rows = db.rows(cur, f"""SELECT {SITE_COLS},
                                   count(*) FILTER (WHERE l.src_table = 'reg_nsq' AND l.confidence >= {HIGH}) AS nsq,
                                   count(*) FILTER (WHERE l.src_table = 'usfda_actions' AND l.confidence >= {HIGH}) AS usfda,
                                   count(*) FILTER (WHERE l.src_table = 'reg_approvals' AND l.confidence >= {HIGH}) AS approvals,
                                   count(*) FILTER (WHERE l.src_table = 'firm_debarments' AND l.confidence >= {HIGH}) AS debarments,
                                   max(n.alert_month) AS last_nsq
                               FROM sites s LEFT JOIN entity_links l ON l.linker = 'site:records' AND l.dst_id = s.site_key
                               LEFT JOIN reg_nsq n ON l.src_table = 'reg_nsq' AND CAST(n.id AS VARCHAR) = l.src_key
                               WHERE {where} GROUP BY ALL ORDER BY usfda DESC, nsq DESC, s.records DESC LIMIT {int(limit)}""", args)
    except Exception:  # noqa: BLE001 — before the first site run
        return []
    for r in rows:
        r["roles"] = json.loads(r["roles"] or "{}")
    return cleanrows(rows)


@router.get("/{key:path}")
def site(key: str):
    cur = db.cursor()
    s = db.one(cur, f"""SELECT {SITE_COLS}, s.company_id, s.parent_id, s.auto_group, c.name AS company, c.slug AS company_slug,
                              pa.name AS parent, pa.slug AS parent_slug
                       FROM sites s LEFT JOIN companies c ON c.id = s.company_id LEFT JOIN parents pa ON pa.id = s.parent_id
                       WHERE s.site_key = ?""", [key])
    if not s:
        raise HTTPException(404, "site not found")
    s["roles"] = json.loads(s["roles"] or "{}")
    s["nsq"] = _recs(cur, "reg_nsq", "t.alert_month, t.category, t.product_text, t.batch_no, t.reason, t.source_url", "CAST(t.id AS VARCHAR)", key,
                     "t.alert_month DESC NULLS LAST")
    s["usfda"] = _recs(cur, "usfda_actions", "t.issued_on, t.kind, t.firm, t.subject, t.url", "CAST(t.id AS VARCHAR)", key, "t.issued_on DESC NULLS LAST")
    s["approvals"] = _recs(cur, "reg_approvals", "t.approved_on, t.drug_text, t.approval_type, t.applicant, t.source_url", "CAST(t.id AS VARCHAR)", key,
                           "t.approved_on DESC NULLS LAST")
    s["debarments"] = _recs(cur, "firm_debarments", "t.state, t.drug_text, t.reason, t.ordered_on, t.years", "t.dedupe_key", key, "t.ordered_on DESC NULLS LAST")
    s["other_sites"] = summary(cur, "s.maker_key = ? AND s.site_key <> ?", [s["maker_key"], key], 30)
    return cleanrows([s])[0]
