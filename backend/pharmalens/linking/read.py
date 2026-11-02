"""Read derived links for profile pages. Every row carries method, confidence and an `inferred` flag; the UI shows
high-confidence rows by default and labels the rest."""
from .. import db
from .store import HIGH

BR_KEY = ("coalesce(b.license_number, '') || '|' || coalesce(b.brand_norm, '') || '|' || coalesce(b.firm_name, '') || '|' || "
          "md5(coalesce(b.generic_name, ''))")
PR_KEY = ("r.buyer || '|' || coalesce(r.tender_no, '') || '|' || coalesce(r.item_code, '') || '|' || coalesce(r.supplier, '') || '|' || "
          "coalesce(r.unit, '') || '|' || coalesce(r.level, '') || '|' || coalesce(CAST(r.rate AS VARCHAR), '')")


def _q(sql: str, args: list) -> list[dict]:
    try:
        rows = db.rows(db.cursor(), sql, args)
    except Exception:  # noqa: BLE001 — link tables absent (before the first linker run): nothing to show
        return []
    for r in rows:
        r["inferred"] = (r.get("confidence") or 0) < HIGH
    return rows


def for_molecule(mid: int) -> dict:
    k = str(mid)
    L = "FROM entity_links l WHERE l.dst_type = 'molecule' AND l.dst_id = ? AND l.src_table = '{t}'"
    return {
        "brand_registry": _q(f"""SELECT b.brand_name, b.firm_name, b.license_number, b.generic_name, b.company_id, c.slug AS company_slug,
                                        l.method, l.confidence, l.evidence
                                 FROM (SELECT * {L.format(t='brand_registry')}) l
                                 JOIN brand_registry b ON {BR_KEY} = l.src_key LEFT JOIN companies c ON c.id = b.company_id
                                 ORDER BY l.confidence DESC, b.firm_name LIMIT 200""", [k]),
        "brand_registry_total": (_q(f"SELECT count(*) n, count(*) FILTER (WHERE confidence >= {HIGH}) high, 0 confidence {L.format(t='brand_registry')}", [k])
                                 or [{}])[0],
        "us_recalls": _q(f"""SELECT a.issued_on, a.firm, a.country, a.subject, a.url, l.method, l.confidence, l.evidence
                             FROM (SELECT * {L.format(t='usfda_actions')}) l JOIN usfda_actions a ON CAST(a.id AS VARCHAR) = l.src_key
                             ORDER BY a.issued_on DESC NULLS LAST LIMIT 40""", [k]),
        "trials": _q(f"""SELECT t.nct_id, t.title, t.sponsor, t.phase, t.status, t.last_update, l.method, l.confidence, l.evidence
                         FROM (SELECT * {L.format(t='trials')}) l JOIN trials t ON t.nct_id = l.src_key
                         WHERE NOT list_contains(string_split(coalesce(t.molecule_ids, ''), ','), ?)
                         ORDER BY t.last_update DESC NULLS LAST LIMIT 30""", [k, k]),
        "news": _q(f"""SELECT n.id, n.published_at, n.source, n.title, n.url, n.topic, l.method, l.confidence, l.evidence
                       FROM (SELECT * {L.format(t='news')}) l JOIN news n ON CAST(n.id AS VARCHAR) = l.src_key
                       WHERE NOT list_contains(string_split(coalesce(n.molecule_ids, ''), ','), ?)
                       ORDER BY n.published_at DESC LIMIT 30""", [k, k]),
        "tenders": _q(f"""SELECT r.buyer, r.item, r.supplier, r.unit, r.rate, r.level, r.valid_to, l.method, l.confidence, l.evidence
                          FROM (SELECT * {L.format(t='procurement_rates')}) l JOIN procurement_rates r ON {PR_KEY} = l.src_key
                          WHERE NOT list_contains(string_split(coalesce(r.molecule_ids, ''), ','), ?)
                          ORDER BY r.rate LIMIT 40""", [k, k]),
    }
