"""Government desk: NSQ/spurious batches, banned FDCs, regulator documents, recalls, Jan Aushadhi."""
from fastapi import APIRouter, Query

from ... import db
from ...normalize import norm
from ..common import cleanrows, csv_response, paged

router = APIRouter(prefix="/reg", tags=["regulatory"])


@router.get("/summary")
def summary():
    cur = db.cursor()
    s = db.one(cur, """SELECT
        (SELECT count(*) FROM reg_nsq) nsq, (SELECT count(*) FROM reg_nsq WHERE category='SPURIOUS') spurious,
        (SELECT max(alert_month) FROM reg_nsq) nsq_latest,
        (SELECT count(*) FROM reg_banned_fdc WHERE status='banned') banned, (SELECT count(*) FROM reg_banned_fdc WHERE status='restricted') restricted,
        (SELECT max(notified_on) FROM reg_banned_fdc) last_ban,
        (SELECT count(*) FROM combos WHERE banned_skus > 0) banned_combos_in_catalog,
        (SELECT count(*) FROM products WHERE ban_level = 'exact') banned_skus_in_catalog,
        (SELECT count(*) FROM products WHERE ban_level = 'review') ban_review_skus,
        (SELECT count(*) FROM reg_documents) documents, (SELECT max(published_on) FROM reg_documents) last_document,
        (SELECT count(*) FROM usfda_actions) usfda, (SELECT count(*) FROM jan_aushadhi) jan_aushadhi""")
    by_month = db.rows(cur, """SELECT alert_month, count(*) FILTER (WHERE category='NSQ') nsq, count(*) FILTER (WHERE category='SPURIOUS') spurious
                               FROM reg_nsq WHERE alert_month >= '2022-01' GROUP BY 1 ORDER BY 1""")
    reasons = db.rows(cur, """SELECT CASE
            WHEN reason ILIKE '%dissolution%' THEN 'Dissolution' WHEN reason ILIKE '%assay%' THEN 'Assay'
            WHEN reason ILIKE '%steril%' THEN 'Sterility' WHEN reason ILIKE '%particulate%' THEN 'Particulate matter'
            WHEN reason ILIKE '%description%' THEN 'Description' WHEN reason ILIKE '%identif%' THEN 'Identification'
            WHEN reason ILIKE '%related substance%' OR reason ILIKE '%impurit%' THEN 'Impurities'
            WHEN reason ILIKE '%disintegr%' THEN 'Disintegration' WHEN reason ILIKE '%spurious%' THEN 'Spurious'
            WHEN reason ILIKE '%label%' OR reason ILIKE '%misbrand%' THEN 'Labelling/Misbranded'
            WHEN reason ILIKE '%ph%' THEN 'pH' WHEN reason ILIKE '%weight%' OR reason ILIKE '%volume%' THEN 'Weight/Volume'
            ELSE 'Other' END AS reason, count(*) n FROM reg_nsq GROUP BY 1 ORDER BY 2 DESC""")
    repeat = db.rows(cur, """SELECT c.name, c.slug, count(*) n, max(n.alert_month) latest FROM reg_nsq n JOIN companies c ON c.id = n.company_id
                             GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 15""")
    return {"summary": cleanrows([s])[0], "by_month": cleanrows(by_month), "reasons": cleanrows(reasons), "repeat_offenders": cleanrows(repeat)}


@router.get("/nsq")
def nsq(q: str | None = None, category: str | None = None, month: str | None = None, company_id: int | None = None,
        molecule_id: int | None = None, batch: str | None = None, page: int = 1, limit: int = Query(50, le=1000), format: str = "json"):
    where, args = ["1=1"], []
    if q:
        where.append("(lower(product_text) LIKE ? OR lower(manufacturer) LIKE ?)"); args += [f"%{q.lower()}%"] * 2
    if category:
        where.append("category = ?"); args.append(category.upper())
    if month:
        where.append("alert_month = ?"); args.append(month)
    if company_id:
        where.append("company_id = ?"); args.append(company_id)
    if molecule_id:
        where.append("list_contains(string_split(molecule_ids, ','), ?)"); args.append(str(molecule_id))
    if batch:
        where.append("upper(replace(batch_no, ' ', '')) = ?"); args.append(batch.upper().replace(" ", ""))
    w = " AND ".join(where)
    cur = db.cursor()
    sql = f"""SELECT n.id, n.alert_month, n.category, n.product_text, n.batch_no, n.mfg_date, n.exp_date, n.manufacturer, n.reason,
                     n.lab, n.source_url, n.company_id, c.slug company_slug, pa.name parent
              FROM reg_nsq n LEFT JOIN companies c ON c.id = n.company_id LEFT JOIN parents pa ON pa.id = c.parent_id
              WHERE {w} ORDER BY n.alert_month DESC NULLS LAST, n.id DESC"""
    if format == "csv":
        return csv_response(db.rows(cur, sql + " LIMIT 100000", args), "nsq_batches")
    total = cur.execute(f"SELECT count(*) FROM reg_nsq WHERE {w}", args).fetchone()[0]
    return paged(total, page, limit, db.rows(cur, sql + " LIMIT ? OFFSET ?", args + [limit, (page - 1) * limit]))


@router.get("/bans")
def bans(q: str | None = None, status: str | None = None, page: int = 1, limit: int = Query(100, le=1000), format: str = "json"):
    where, args = ["1=1"], []
    if q:
        where.append("lower(b.combo_text) LIKE ?"); args.append(f"%{q.lower()}%")
    if status:
        where.append("b.status = ?"); args.append(status)
    w = " AND ".join(where)
    cur = db.cursor()
    sql = f"""SELECT b.id, b.combo_text, b.mkey, b.notification, b.notified_on, b.status, b.source_url,
                     count(p.id) FILTER (WHERE p.ban_level = 'exact') AS catalog_skus,
                     count(p.id) FILTER (WHERE p.ban_level = 'review') AS review_skus,
                     count(DISTINCT p.company_id) AS catalog_companies
              FROM reg_banned_fdc b LEFT JOIN products p ON p.ban_id = b.id
              WHERE {w} GROUP BY ALL ORDER BY b.notified_on DESC NULLS LAST, b.id DESC"""
    if format == "csv":
        return csv_response(db.rows(cur, sql, args), "banned_fdcs")
    total = cur.execute(f"SELECT count(*) FROM reg_banned_fdc b WHERE {w}", args).fetchone()[0]
    return paged(total, page, limit, db.rows(cur, sql + " LIMIT ? OFFSET ?", args + [limit, (page - 1) * limit]))


@router.get("/bans/{bid}/products")
def ban_products(bid: int, limit: int = Query(500, le=5000)):
    cur = db.cursor()
    b = db.one(cur, "SELECT * FROM reg_banned_fdc WHERE id = ?", [bid])
    if not b:
        return {"ban": None, "data": []}
    data = db.rows(cur, """SELECT p.id, p.name, p.mrp, p.pack_size, p.dosage_form, p.ban_level, p.is_discontinued, p.in_stock,
                                  c.name company, c.slug company_slug, k.label
                           FROM products p LEFT JOIN combos k ON k.id = p.combo_id LEFT JOIN companies c ON c.id = p.company_id
                           WHERE p.ban_id = ? ORDER BY p.ban_level, p.is_discontinued NULLS FIRST, p.source_count DESC LIMIT ?""", [bid, limit])
    return {"ban": cleanrows([b])[0], "data": cleanrows(data)}


@router.get("/documents")
def documents(agency: str | None = None, doc_type: str | None = None, q: str | None = None,
              page: int = 1, limit: int = Query(50, le=500)):
    where, args = ["1=1"], []
    if agency:
        where.append("agency = ?"); args.append(agency)
    if doc_type:
        where.append("doc_type = ?"); args.append(doc_type)
    if q:
        where.append("lower(title) LIKE ?"); args.append(f"%{q.lower()}%")
    w = " AND ".join(where)
    cur = db.cursor()
    total = cur.execute(f"SELECT count(*) FROM reg_documents WHERE {w}", args).fetchone()[0]
    data = db.rows(cur, f"SELECT * FROM reg_documents WHERE {w} ORDER BY published_on DESC NULLS LAST, id DESC LIMIT ? OFFSET ?",
                   args + [limit, (page - 1) * limit])
    types = db.rows(cur, "SELECT agency, doc_type, count(*) n, max(published_on) latest FROM reg_documents GROUP BY 1, 2 ORDER BY 1, 3 DESC")
    return paged(total, page, limit, data, types=cleanrows(types))


@router.get("/usfda")
def usfda(parent_id: int | None = None, page: int = 1, limit: int = Query(50, le=500)):
    where, args = ["1=1"], []
    if parent_id:
        where.append("u.parent_id = ?"); args.append(parent_id)
    w = " AND ".join(where)
    cur = db.cursor()
    total = cur.execute(f"SELECT count(*) FROM usfda_actions u WHERE {w}", args).fetchone()[0]
    data = db.rows(cur, f"""SELECT u.*, pa.name parent, pa.slug parent_slug FROM usfda_actions u LEFT JOIN parents pa ON pa.id = u.parent_id
                            WHERE {w} ORDER BY u.issued_on DESC NULLS LAST LIMIT ? OFFSET ?""", args + [limit, (page - 1) * limit])
    return paged(total, page, limit, data)


@router.get("/jan-aushadhi")
def jan_aushadhi(q: str | None = None, group: str | None = None, page: int = 1, limit: int = Query(50, le=3000)):
    where, args = ["1=1"], []
    if q:
        where.append("lower(name) LIKE ?"); args.append(f"%{q.lower()}%")
    if group:
        where.append("group_name = ?"); args.append(group)
    w = " AND ".join(where)
    cur = db.cursor()
    total = cur.execute(f"SELECT count(*) FROM jan_aushadhi WHERE {w}", args).fetchone()[0]
    data = db.rows(cur, f"SELECT * FROM jan_aushadhi WHERE {w} ORDER BY CAST(drug_code AS INT) LIMIT ? OFFSET ?",
                   args + [limit, (page - 1) * limit])
    groups = db.rows(cur, "SELECT group_name, count(*) n FROM jan_aushadhi GROUP BY 1 ORDER BY 2 DESC")
    return paged(total, page, limit, data, groups=cleanrows(groups))


@router.get("/nppa-ceiling")
def nppa_ceiling(q: str | None = None, limit: int = Query(200, le=2000)):
    cur = db.cursor()
    where, args = ["1=1"], []
    if q:
        where.append("lower(molecule_name) LIKE ?"); args.append(f"%{norm(q)}%")
    data = db.rows(cur, f"""SELECT n.*, m.product_count FROM nppa_ceiling n LEFT JOIN molecules m ON m.id = n.molecule_id
                            WHERE {' AND '.join(where)} ORDER BY n.year DESC, n.molecule_name LIMIT ?""", args + [limit])
    return {"data": cleanrows(data)}


@router.get("/shortages")
def shortages(region: str | None = None, limit: int = Query(200, le=2000)):
    cur = db.cursor()
    where, args = ["1=1"], []
    if region:
        where.append("region = ?"); args.append(region)
    data = db.rows(cur, f"SELECT * FROM shortages WHERE {' AND '.join(where)} ORDER BY updated_on DESC NULLS LAST LIMIT ?", args + [limit])
    return {"data": cleanrows(data)}
