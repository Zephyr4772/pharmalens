"""Pipeline: CDSCO approvals, SEC recommendations, clinical trials, NLEM."""
from fastapi import APIRouter, Query

from ... import db
from ..common import cleanrows, csv_response, paged

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("/summary")
def summary():
    cur = db.cursor()
    k = db.one(cur, """SELECT
        (SELECT count(*) FROM reg_approvals) approvals,
        (SELECT max(approved_on) FROM reg_approvals) last_approval,
        (SELECT count(*) FROM sec_items) sec_items,
        (SELECT max(meeting_date) FROM sec_items) last_sec,
        (SELECT count(*) FROM sec_items WHERE outcome = 'recommended' AND meeting_date >= current_date - INTERVAL 90 DAY) sec_recommended_90d,
        (SELECT count(*) FROM sec_items WHERE division = 'new_drug' AND outcome = 'recommended' AND meeting_date >= current_date - INTERVAL 365 DAY) marketing_12m,
        (SELECT count(*) FROM trials) trials,
        (SELECT count(*) FROM trials WHERE status IN ('RECRUITING', 'NOT_YET_RECRUITING')) trials_recruiting,
        (SELECT count(DISTINCT molecule_name) FROM nlem) nlem_medicines""")
    approvals_by_year = db.rows(cur, "SELECT year(approved_on) y, count(*) n FROM reg_approvals WHERE approved_on >= DATE '2015-01-01' GROUP BY 1 ORDER BY 1")
    sec_matrix = db.rows(cur, """SELECT division, outcome, count(*) n FROM sec_items
                                 WHERE meeting_date >= current_date - INTERVAL 365 DAY GROUP BY 1, 2 ORDER BY 1, 3 DESC""")
    committees = db.rows(cur, """SELECT committee, count(*) n, count(*) FILTER (WHERE outcome = 'recommended') rec, max(meeting_date) latest
                                 FROM sec_items GROUP BY 1 ORDER BY 2 DESC LIMIT 25""")
    sponsors = db.rows(cur, """SELECT coalesce(pa.name, t.sponsor) sponsor, pa.slug, count(*) n,
                                      count(*) FILTER (WHERE t.status IN ('RECRUITING','NOT_YET_RECRUITING','ACTIVE_NOT_RECRUITING')) active
                               FROM trials t LEFT JOIN parents pa ON pa.id = t.parent_id
                               GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20""")
    sec_firms = db.rows(cur, """SELECT coalesce(pa.name, s.firm) firm, pa.slug, count(*) n,
                                       count(*) FILTER (WHERE s.outcome = 'recommended') rec
                                FROM sec_items s LEFT JOIN parents pa ON pa.id = s.parent_id
                                WHERE s.meeting_date >= current_date - INTERVAL 365 DAY
                                GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20""")
    phases = db.rows(cur, "SELECT coalesce(phase, 'N/A') phase, count(*) n FROM trials WHERE status IN ('RECRUITING','NOT_YET_RECRUITING','ACTIVE_NOT_RECRUITING') GROUP BY 1 ORDER BY 2 DESC")
    return {"kpis": cleanrows([k])[0], "approvals_by_year": cleanrows(approvals_by_year), "sec_matrix": cleanrows(sec_matrix),
            "committees": cleanrows(committees), "sponsors": cleanrows(sponsors), "sec_firms": cleanrows(sec_firms), "phases": cleanrows(phases)}


@router.get("/approvals")
def approvals(q: str | None = None, year: int | None = None, page: int = 1, limit: int = Query(60, le=1000), format: str = "json"):
    where, args = ["1=1"], []
    if q:
        where.append("(lower(drug_text) LIKE ? OR lower(indication) LIKE ?)"); args += [f"%{q.lower()}%"] * 2
    if year:
        where.append("year(approved_on) = ?"); args.append(year)
    w = " AND ".join(where)
    cur = db.cursor()
    sql = f"SELECT id, drug_text, indication, approved_on, molecule_ids, source_url FROM reg_approvals WHERE {w} ORDER BY approved_on DESC NULLS LAST"
    if format == "csv":
        return csv_response(db.rows(cur, sql, args), "cdsco_new_drug_approvals")
    total = cur.execute(f"SELECT count(*) FROM reg_approvals WHERE {w}", args).fetchone()[0]
    return paged(total, page, limit, db.rows(cur, sql + " LIMIT ? OFFSET ?", args + [limit, (page - 1) * limit]))


@router.get("/sec")
def sec(q: str | None = None, division: str | None = None, outcome: str | None = None, committee: str | None = None,
        parent_id: int | None = None, molecule_id: int | None = None, page: int = 1, limit: int = Query(50, le=1000), format: str = "json"):
    where, args = ["1=1"], []
    if q:
        where.append("(lower(s.drug_text) LIKE ? OR lower(s.firm) LIKE ?)"); args += [f"%{q.lower()}%"] * 2
    if division:
        where.append("s.division = ?"); args.append(division)
    if outcome:
        where.append("s.outcome = ?"); args.append(outcome)
    if committee:
        where.append("s.committee = ?"); args.append(committee)
    if parent_id:
        where.append("s.parent_id = ?"); args.append(parent_id)
    if molecule_id:
        where.append("list_contains(string_split(s.molecule_ids, ','), ?)"); args.append(str(molecule_id))
    w = " AND ".join(where)
    cur = db.cursor()
    sql = f"""SELECT s.id, s.meeting_date, s.committee, s.division, s.file_no, s.drug_text, s.firm, s.outcome, s.recommendation,
                     s.source_url, pa.name parent, pa.slug parent_slug, c.slug company_slug
              FROM sec_items s LEFT JOIN parents pa ON pa.id = s.parent_id LEFT JOIN companies c ON c.id = s.company_id
              WHERE {w} ORDER BY s.meeting_date DESC NULLS LAST, s.id"""
    if format == "csv":
        return csv_response(db.rows(cur, sql, args), "sec_recommendations")
    total = cur.execute(f"SELECT count(*) FROM sec_items s WHERE {w}", args).fetchone()[0]
    committees = [r[0] for r in cur.execute("SELECT committee FROM sec_items GROUP BY 1 ORDER BY count(*) DESC").fetchall()]
    return paged(total, page, limit, db.rows(cur, sql + " LIMIT ? OFFSET ?", args + [limit, (page - 1) * limit]), committees=committees)


@router.get("/trials")
def trials(q: str | None = None, status: str | None = None, phase: str | None = None, parent_id: int | None = None,
           molecule_id: int | None = None, indian_sponsor: bool | None = None, page: int = 1, limit: int = Query(50, le=1000), format: str = "json"):
    where, args = ["1=1"], []
    if q:
        where.append("(lower(t.title) LIKE ? OR lower(t.interventions) LIKE ? OR lower(t.sponsor) LIKE ? OR lower(t.conditions) LIKE ?)"); args += [f"%{q.lower()}%"] * 4
    if status == "active":
        where.append("t.status IN ('RECRUITING','NOT_YET_RECRUITING','ACTIVE_NOT_RECRUITING','ENROLLING_BY_INVITATION')")
    elif status:
        where.append("t.status = ?"); args.append(status)
    if phase:
        where.append("t.phase LIKE ?"); args.append(f"%{phase}%")
    if parent_id:
        where.append("t.parent_id = ?"); args.append(parent_id)
    if molecule_id:
        where.append("list_contains(string_split(t.molecule_ids, ','), ?)"); args.append(str(molecule_id))
    if indian_sponsor:
        where.append("pa.ownership LIKE 'indian%'")
    w = " AND ".join(where)
    cur = db.cursor()
    sql = f"""SELECT t.*, pa.name parent, pa.slug parent_slug FROM trials t LEFT JOIN parents pa ON pa.id = t.parent_id
              WHERE {w} ORDER BY t.last_update DESC NULLS LAST"""
    if format == "csv":
        return csv_response(db.rows(cur, sql, args), "india_trials")
    total = cur.execute(f"SELECT count(*) FROM trials t LEFT JOIN parents pa ON pa.id = t.parent_id WHERE {w}", args).fetchone()[0]
    return paged(total, page, limit, db.rows(cur, sql + " LIMIT ? OFFSET ?", args + [limit, (page - 1) * limit]))


@router.get("/nlem")
def nlem(q: str | None = None, section: str | None = None, limit: int = Query(1000, le=2000)):
    where, args = ["1=1"], []
    if q:
        where.append("lower(n.molecule_name) LIKE ?"); args.append(f"%{q.lower()}%")
    if section:
        where.append("n.section = ?"); args.append(section)
    cur = db.cursor()
    data = db.rows(cur, f"""SELECT n.*, m.name molecule, m.product_count, m.nppa_ceiling FROM nlem n LEFT JOIN molecules m ON m.id = n.molecule_id
                            WHERE {' AND '.join(where)} ORDER BY n.section, n.molecule_name LIMIT ?""", args + [limit])
    sections = db.rows(cur, "SELECT section, count(*) n FROM nlem GROUP BY 1 ORDER BY 1")
    return {"data": cleanrows(data), "sections": cleanrows(sections)}


@router.get("/new-brands")
def new_brands(days: int = Query(90, le=3650), source: str | None = None, q: str | None = None, page: int = 1,
               limit: int = Query(80, le=1000), format: str = "json"):
    """Brands that appeared in the CDSCO brand registry (since tracking began) or CDCI (by its update date)."""
    where, args = ["f.first_seen >= current_date - ?", "(NOT f.baseline OR f.source = 'cdci')"], [days]
    if source:
        where.append("f.source = ?"); args.append(source)
    if q:
        where.append("(lower(f.brand) LIKE ? OR lower(f.firm) LIKE ? OR lower(coalesce(f.generic, '')) LIKE ?)")
        args += [f"%{q.lower()}%"] * 3
    w = " AND ".join(where)
    # in the catalog already = an existing product's name starts with the brand (a new pack, not a new brand)
    sql = f"""SELECT f.first_seen, f.source, f.brand, f.generic, f.firm, f.license, c.name AS company, c.slug AS company_slug,
                     pa.name AS parent, pa.slug AS parent_slug,
                     EXISTS (SELECT 1 FROM products p WHERE p.name_norm = f.brand_norm OR p.name_norm LIKE f.brand_norm || ' %') AS in_catalog
              FROM brand_first_seen f LEFT JOIN companies c ON c.id = f.company_id LEFT JOIN parents pa ON pa.id = c.parent_id
              WHERE {w} ORDER BY f.first_seen DESC, f.firm, f.brand"""
    cur = db.cursor()
    if format == "csv":
        return csv_response(db.rows(cur, sql + " LIMIT 100000", args), "new_brand_registrations")
    total = cur.execute(f"SELECT count(*) FROM brand_first_seen f WHERE {w}", args).fetchone()[0]
    data = db.rows(cur, sql + " LIMIT ? OFFSET ?", args + [limit, (page - 1) * limit])
    tracking = cur.execute("SELECT source, min(first_seen) FILTER (WHERE baseline), count(*) FILTER (WHERE NOT baseline) FROM brand_first_seen GROUP BY 1").fetchall()
    return paged(total, page, limit, data, tracking=[{"source": s, "since": d, "new": n} for s, d, n in tracking])
