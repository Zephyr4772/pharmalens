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
    last = _last_inspections(cur, [r["site_key"] for r in rows])
    for r in rows:
        r.update(last.get(r["site_key"], {}))
    return cleanrows(rows)


def _last_inspections(cur, keys: list[str]) -> dict[str, dict]:
    """Latest US FDA inspection per site (classification, date, 483 citations), when the inspections feed is loaded."""
    if not keys:
        return {}
    try:
        rows = cur.execute(f"""SELECT l.dst_id, arg_max(i.classification, i.end_date), max(i.end_date), count(*),
                                      count(*) FILTER (WHERE i.classification ILIKE '%official action%')
                               FROM entity_links l JOIN fda_inspections i ON i.inspection_id = l.src_key
                               WHERE l.linker = 'site:records' AND l.src_table = 'fda_inspections' AND l.dst_id IN ({','.join('?' * len(keys))})
                               GROUP BY 1""", keys).fetchall()
    except Exception:  # noqa: BLE001 — inspections feed not loaded yet
        return {}
    out = {k: {"last_inspection_class": c, "last_inspection": d, "inspections": n, "oai": o} for k, c, d, n, o in rows}
    try:
        for k, wl, last, ir in cur.execute(f"""SELECT l.dst_id, count(a.case_id), max(a.action_date), count(*) FILTER (WHERE l.src_table = 'fda_import_refusals')
                                               FROM entity_links l LEFT JOIN fda_compliance_actions a ON l.src_table = 'fda_compliance_actions'
                                                    AND a.case_id = l.src_key
                                               WHERE l.linker = 'site:records' AND l.confidence >= {HIGH}
                                                 AND l.src_table IN ('fda_compliance_actions', 'fda_import_refusals')
                                                 AND l.dst_id IN ({','.join('?' * len(keys))}) GROUP BY 1""", keys).fetchall():
            out.setdefault(k, {}).update({"warning_letters": wl, "last_warning": last, "refusals": ir})
    except Exception:  # noqa: BLE001 — compliance feed not loaded yet
        pass
    return out


def group_fda(cur, parent_id: int) -> dict:
    """US FDA plant record for a group's sites (high-confidence links): OAI inspections and warning letters in 2 years,
    refused shipments in 12 months. Empty when the Data Dashboard feeds are not loaded."""
    def one(select: str, table: str, key: str, when: str):
        return cur.execute(f"""SELECT {select} FROM entity_links l JOIN sites s ON s.site_key = l.dst_id JOIN {table} t ON {key} = l.src_key
                               WHERE l.linker = 'site:records' AND l.src_table = '{table}' AND l.confidence >= {HIGH}
                                 AND s.parent_id = ? AND {when}""", [parent_id]).fetchone()
    try:
        oai, n = one("count(*) FILTER (WHERE t.classification ILIKE '%official action%'), count(*)", "fda_inspections", "t.inspection_id",
                     "t.end_date >= current_date - INTERVAL 2 YEAR")
        wl, last = one("count(*), max(t.action_date)", "fda_compliance_actions", "t.case_id", "t.action_date >= current_date - INTERVAL 2 YEAR")
        ir = one("count(*)", "fda_import_refusals", "t.shipment_id || '|' || t.product_code", "t.refusal_date >= current_date - INTERVAL 1 YEAR")[0]
    except Exception:  # noqa: BLE001 — Data Dashboard feeds not loaded yet
        return {}
    return {"oai_2y": oai, "inspections_2y": n, "wl_2y": wl, "last_wl": last, "refusals_1y": ir}


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
    try:
        s["inspections"] = _recs(cur, "fda_inspections", """t.inspection_id, t.fei, t.end_date, t.classification, t.project_area, t.posted_citations,
                                 (SELECT count(*) FROM fda_citations c WHERE c.inspection_id = t.inspection_id) AS citations""",
                                 "t.inspection_id", key, "t.end_date DESC NULLS LAST")
        s["citations"] = db.rows(cur, """SELECT c.inspection_id, c.end_date, c.act_cfr, c.short_desc, c.long_desc FROM fda_citations c
                                         WHERE c.inspection_id IN (SELECT src_key FROM entity_links WHERE linker = 'site:records'
                                         AND src_table = 'fda_inspections' AND dst_id = ?) ORDER BY c.end_date DESC LIMIT 80""", [key])
    except Exception:  # noqa: BLE001 — inspections feed not loaded yet
        s["inspections"], s["citations"] = [], []
    try:
        s["compliance"] = _recs(cur, "fda_compliance_actions", "t.case_id, t.fei, t.action_date, t.action_type, t.center, t.firm", "t.case_id", key,
                                "t.action_date DESC NULLS LAST")
        s["refusals"] = _recs(cur, "fda_import_refusals", "t.refusal_date, t.fei, t.product, t.product_code, t.charges, t.fda_sample, t.shipment_id",
                              "t.shipment_id || '|' || t.product_code", key, "t.refusal_date DESC NULLS LAST")
    except Exception:  # noqa: BLE001 — compliance feed not loaded yet
        s["compliance"], s["refusals"] = [], []
    s["other_sites"] = summary(cur, "s.maker_key = ? AND s.site_key <> ?", [s["maker_key"], key], 30)
    return cleanrows([s])[0]
