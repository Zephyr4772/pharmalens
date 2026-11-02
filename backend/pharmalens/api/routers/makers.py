"""Maker (manufacturing firm) profiles: every record that names the firm, by role, and who it makes for (plant stage 1)."""
import json

from fastapi import APIRouter, HTTPException, Query

from ... import db
from ...linking.store import HIGH
from ..common import cleanrows

router = APIRouter(prefix="/makers", tags=["makers"])


def _recs(cur, table: str, cols: str, key_expr: str, mk: str, order: str, limit: int = 60) -> list[dict]:
    return db.rows(cur, f"""SELECT {cols}, l.confidence, l.method, l.confidence < {HIGH} AS inferred FROM entity_links l
                            JOIN {table} t ON {key_expr} = l.src_key
                            WHERE l.linker = 'maker:{table}' AND l.dst_id = ? ORDER BY {order} LIMIT {limit}""", [mk])


@router.get("")
def search(q: str = Query("", min_length=0), limit: int = Query(30, le=100)):
    cur = db.cursor()
    rows = db.rows(cur, """SELECT m.maker_key, m.name, m.records, m.roles, m.distinctive, c.name AS company, pa.name AS parent
                           FROM makers m LEFT JOIN companies c ON c.id = m.company_id LEFT JOIN parents pa ON pa.id = m.parent_id
                           WHERE lower(m.name) LIKE ? ORDER BY m.records DESC LIMIT ?""", [f"%{q.lower()}%", limit])
    return {"data": cleanrows(rows)}


@router.get("/{key:path}")
def maker(key: str):
    cur = db.cursor()
    m = db.one(cur, """SELECT m.*, c.name AS company, c.slug AS company_slug, pa.name AS parent, pa.slug AS parent_slug, ag.name AS auto_group_name
                       FROM makers m LEFT JOIN companies c ON c.id = m.company_id LEFT JOIN parents pa ON pa.id = m.parent_id
                       LEFT JOIN auto_groups ag ON ag.group_key = m.auto_group WHERE m.maker_key = ?""", [key])
    if not m:
        raise HTTPException(404, "maker not found")
    m["roles"] = json.loads(m["roles"] or "{}")
    br = ("coalesce(t.license_number, '') || '|' || coalesce(t.brand_norm, '') || '|' || coalesce(t.firm_name, '') || '|' || "
          "md5(coalesce(t.generic_name, ''))")
    pr = ("t.buyer || '|' || coalesce(t.tender_no, '') || '|' || coalesce(t.item_code, '') || '|' || coalesce(t.supplier, '') || '|' || "
          "coalesce(t.unit, '') || '|' || coalesce(t.level, '') || '|' || coalesce(CAST(t.rate AS VARCHAR), '')")
    m["nsq"] = _recs(cur, "reg_nsq", "t.alert_month, t.category, t.product_text, t.batch_no, t.reason, t.manufacturer, t.source_url",
                     "CAST(t.id AS VARCHAR)", key, "t.alert_month DESC NULLS LAST")
    m["usfda"] = _recs(cur, "usfda_actions", "t.issued_on, t.kind, t.firm, t.country, t.subject, t.url", "CAST(t.id AS VARCHAR)", key, "t.issued_on DESC NULLS LAST")
    m["approvals"] = _recs(cur, "reg_approvals", "t.approved_on, t.drug_text, t.approval_type, t.applicant, t.source_url", "CAST(t.id AS VARCHAR)",
                           key, "t.approved_on DESC NULLS LAST")
    m["tenders"] = _recs(cur, "procurement_rates", "t.buyer, t.item, t.unit, t.rate, t.level, t.valid_to", pr, key, "t.buyer, t.item", 40)
    m["debarments"] = _recs(cur, "firm_debarments", "t.state, t.drug_text, t.reason, t.ordered_on, t.years, t.document_url", "t.dedupe_key", key,
                            "t.ordered_on DESC NULLS LAST")
    m["brand_registrations"] = db.rows(cur, f"""
        SELECT t.brand_name, t.generic_name, t.license_number, t.firm_name, p.id AS product_id, p.name AS product, co.name AS marketer, co.slug AS marketer_slug,
               bp.confidence AS sku_confidence, bp.confidence < {HIGH} AS sku_inferred
        FROM entity_links l JOIN brand_registry t ON {br} = l.src_key
        LEFT JOIN entity_links bp ON bp.linker = 'maker:brand_product' AND bp.src_key = l.src_key
        LEFT JOIN products p ON CAST(p.id AS VARCHAR) = bp.dst_id LEFT JOIN companies co ON co.id = p.company_id
        WHERE l.linker = 'maker:brand_registry' AND l.dst_id = ?
        ORDER BY (p.id IS NULL), bp.confidence DESC NULLS LAST, t.brand_name LIMIT 120""", [key])
    m["cdci_suppliers"] = cur.execute("SELECT count(*) FROM entity_links WHERE linker = 'maker:cdci_supplier' AND dst_id = ?", [key]).fetchone()[0]
    m["makes_for"] = db.rows(cur, """SELECT f.relation, f.skus, f.brands, f.example, f.confidence, c.id AS company_id, c.name AS company, c.slug AS company_slug,
                                            pa.name AS parent, pa.slug AS parent_slug
                                     FROM maker_makes_for f JOIN companies c ON c.id = f.company_id LEFT JOIN parents pa ON pa.id = c.parent_id
                                     WHERE f.maker_key = ? ORDER BY f.relation = 'own' DESC, f.skus DESC LIMIT 60""", [key])
    return cleanrows([m])[0]


def made_by(cur, company_id: int) -> list[dict]:
    """Makers that hold brand registrations for this marketer's SKUs (own, same group or contract)."""
    try:
        return cleanrows(db.rows(cur, """SELECT f.relation, f.skus, f.brands, f.example, f.confidence, m.maker_key, m.name AS maker
                                         FROM maker_makes_for f JOIN makers m ON m.maker_key = f.maker_key
                                         WHERE f.company_id = ? ORDER BY f.relation = 'own' DESC, f.skus DESC LIMIT 40""", [company_id]))
    except Exception:  # noqa: BLE001 — before the first maker run
        return []
