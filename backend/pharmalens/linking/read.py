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


def set_of_combo(combo_id: int | None) -> str | None:
    if combo_id is None:
        return None
    r = _q("""SELECT dst_id, 1.0 confidence FROM entity_links WHERE src_table = 'combos' AND src_key = ? AND dst_type = 'ingredient_set'""",
           [str(combo_id)])
    return r[0]["dst_id"] if r else None


def us_eu_status(ingredient_set: str | None) -> dict | None:
    """US (Orange Book, patents, exclusivities) and EU (EMA) records with exactly this ingredient set."""
    if not ingredient_set:
        return None
    ob = _q("""SELECT o.application_number, o.product_number, o.brand, o.ingredients, o.strengths, o.dosage_form, o.app_type, o.rld,
                      o.marketing_status, o.approval_date, o.applicant, pa.name AS parent, pa.slug AS parent_slug, l.method, l.confidence, l.evidence
               FROM entity_links l JOIN us_orange_book o ON o.application_number || '|' || o.product_number = l.src_key
               LEFT JOIN parents pa ON pa.id = o.parent_id
               WHERE l.src_table = 'us_orange_book' AND l.dst_type = 'ingredient_set' AND l.dst_id = ?
               ORDER BY o.approval_date DESC NULLS LAST""", [ingredient_set])
    keys = {(r["application_number"], r["product_number"]) for r in ob}
    pats = [p for p in _q("""SELECT application_number, product_number, kind, code, use_code, expires_on, 0.95 confidence FROM us_patents
                             WHERE application_number IN (SELECT unnest(string_split(?, ',')))
                             AND (expires_on IS NULL OR expires_on >= current_date) ORDER BY expires_on NULLS LAST""",
                          [",".join(sorted({a for a, _ in keys}))]) if (p["application_number"], p["product_number"]) in keys]
    ema = _q("""SELECT e.ema_product_number, e.name_of_medicine, e.medicine_status, e.generic, e.biosimilar,
                       e.marketing_authorisation_developer_applicant_holder AS holder, e.marketing_authorisation_date, l.method, l.confidence, l.evidence
                FROM entity_links l JOIN ema_medicines e ON e.ema_product_number = l.src_key
                WHERE l.src_table = 'ema_medicines' AND l.dst_type = 'ingredient_set' AND l.dst_id = ?
                ORDER BY e.marketing_authorisation_date DESC NULLS LAST""", [ingredient_set])
    anda = [r for r in ob if r["app_type"] == "A"]
    nda = [r for r in ob if r["app_type"] == "N"]
    live = lambda rows: [r for r in rows if (r["marketing_status"] or "").upper() != "DISCONTINUED"]  # noqa: E731
    dated = sorted(p["expires_on"] for p in pats if p["expires_on"])
    return {
        "ingredient_set": ingredient_set,
        "summary": {"nda": len(nda), "anda": len(anda), "anda_marketed": len(live(anda)), "nda_marketed": len(live(nda)),
                    "first_generic": min((r["approval_date"] for r in anda if r["approval_date"]), default=None),
                    "reference_brands": sorted({r["brand"] for r in nda if r["rld"]} or {r["brand"] for r in nda})[:6],
                    "indian_groups": sorted({r["parent"] for r in anda if r["parent"]}),
                    "patents_live": sum(1 for p in pats if p["kind"] == "patent"),
                    "exclusivities_live": sum(1 for p in pats if p["kind"] != "patent"),
                    "protection_until": dated[-1] if dated else None, "next_expiry": dated[0] if dated else None,
                    "ema": len(ema)},
        "orange_book": ob[:40], "patents": pats[:40], "ema": ema[:20],
    }


def timeline(pairs: list[tuple[str, str]], limit: int = 60, require_all: bool = False) -> list[dict]:
    """Events linked to any of (entity_type, entity_id) — or to all of them with require_all — newest first, each with
    the strongest link's method and confidence."""
    if not pairs:
        return []
    cond = " OR ".join("(x.entity_type = ? AND x.entity_id = ?)" for _ in pairs)
    args = [v for p in pairs for v in (p[0], str(p[1]))]
    having = f"HAVING count(DISTINCT x.entity_type || ':' || x.entity_id) = {len(pairs)}" if require_all else ""
    return _q(f"""SELECT e.id, e.ts, e.kind, e.severity, e.title, e.url, e.source,
                         arg_max(x.method, x.confidence) AS method, max(x.confidence) AS confidence, arg_max(x.evidence, x.confidence) AS evidence
                  FROM event_entities x JOIN events e ON e.id = x.event_id
                  WHERE ({cond}) GROUP BY ALL {having}
                  ORDER BY e.ts DESC LIMIT {int(limit)}""", args)


def bans_for_combo(combo_id: int) -> list[dict]:
    return _q("""SELECT b.id, b.combo_text, b.notification, b.notified_on, b.status, b.source_url, l.method, l.confidence, l.evidence
                 FROM entity_links l JOIN reg_banned_fdc b ON CAST(b.id AS VARCHAR) = l.src_key
                 WHERE l.linker = 'bans:combo' AND l.dst_type = 'combo' AND l.dst_id = ? ORDER BY l.confidence DESC, b.notified_on DESC""",
              [str(combo_id)])


def launches(molecule: int | None = None, company: int | None = None, limit: int = 80) -> list[dict]:
    """Dated launch signals (#5) for a molecule (any ingredient set containing it) or a company."""
    if molecule is not None:
        where, args = "list_contains(string_split(l.ingredient_set, ','), ?)", [str(molecule)]
    elif company is not None:
        where, args = "l.company_id = ?", [company]
    else:
        return []
    rows = _q(f"""SELECT l.kind, l.dated_on, l.brand, l.company_id, c.name AS company, c.slug AS company_slug, l.ingredient_set,
                         l.method, l.confidence, l.evidence
                  FROM launch_signals l LEFT JOIN companies c ON c.id = l.company_id
                  WHERE {where} ORDER BY l.dated_on DESC NULLS LAST LIMIT {int(limit)}""", args)
    names = {}
    ids = {i for r in rows for i in (r["ingredient_set"] or "").split(",") if i}
    if ids:
        names = dict(db.cursor().execute(f"SELECT CAST(id AS VARCHAR), name FROM molecules WHERE id IN ({','.join(ids)})").fetchall())
    for r in rows:
        r["ingredients"] = " + ".join(names.get(i, i) for i in (r["ingredient_set"] or "").split(",") if i) or None
    return rows
