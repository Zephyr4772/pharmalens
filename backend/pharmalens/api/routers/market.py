"""Market-level analytics: overview, segments & share, price spreads, launches."""
from fastapi import APIRouter, Query

from ... import db
from ..common import cleanrows, csv_response, paged
from .catalog import share_table

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/overview")
def overview():
    cur = db.cursor()
    k = db.one(cur, """SELECT
        (SELECT count(*) FROM products) products,
        (SELECT count(*) FROM products WHERE coalesce(is_discontinued,false)=false) active_products,
        (SELECT count(*) FROM products WHERE in_stock) in_stock,
        (SELECT count(*) FROM molecules WHERE product_count > 0) molecules,
        (SELECT count(*) FROM combos WHERE molecule_count > 1) fdcs,
        (SELECT count(*) FROM companies WHERE product_count > 0) companies,
        (SELECT count(*) FROM parents) parent_groups,
        (SELECT count(*) FROM combos WHERE banned_skus > 0) banned_combos,
        (SELECT count(*) FROM products WHERE ban_level = 'exact' AND coalesce(is_discontinued,false)=false) banned_skus_listed,
        (SELECT count(*) FROM products WHERE ban_level = 'review' AND coalesce(is_discontinued,false)=false) ban_review_skus,
        (SELECT count(*) FROM reg_nsq) nsq_total,
        (SELECT count(*) FROM reg_nsq WHERE alert_month >= strftime(current_date - INTERVAL 90 DAY, '%Y-%m')) nsq_90d,
        (SELECT max(alert_month) FROM reg_nsq) nsq_latest_month,
        (SELECT count(*) FROM jan_aushadhi) jan_aushadhi_skus,
        (SELECT count(*) FROM events WHERE ts >= now() - INTERVAL 1 DAY) events_24h,
        (SELECT count(*) FROM news WHERE published_at >= now() - INTERVAL 1 DAY) news_24h""")
    classes = db.rows(cur, """
        SELECT st.segment AS therapeutic_class, st.skus, st.owners, st.hhi, st.leader_share,
               coalesce(pa.name, co.name) AS leader,
               (SELECT median(mrp) FROM products p WHERE p.therapeutic_class = st.segment) AS median_mrp
        FROM segment_stats st
        LEFT JOIN parents pa ON st.leader LIKE 'parent:%' AND pa.id = CAST(split_part(st.leader, ':', 2) AS INT)
        LEFT JOIN companies co ON st.leader LIKE 'company:%' AND co.id = CAST(split_part(st.leader, ':', 2) AS INT)
        WHERE st.segment_type = 'class' ORDER BY st.skus DESC""")
    index = db.rows(cur, "SELECT ticker, name, price, change_pct, quoted_at FROM quotes WHERE ticker LIKE '^%' OR ticker LIKE 'NIFTY%'")
    movers = db.rows(cur, """SELECT q.ticker, q.name, q.price, q.change_pct, pa.slug FROM quotes q
                             JOIN parents pa ON pa.ticker || '.NS' = q.ticker
                             WHERE q.change_pct IS NOT NULL ORDER BY abs(q.change_pct) DESC LIMIT 8""")
    groups = db.rows(cur, """
        SELECT pa.slug, pa.name, pa.ticker, sum(s.w) w, sum(s.skus) skus
        FROM segment_share s JOIN parents pa ON s.owner_type = 'parent' AND pa.id = s.owner_id
        WHERE s.segment_type = 'class' GROUP BY ALL ORDER BY w DESC LIMIT 15""")
    tot = cur.execute("SELECT sum(w) FROM segment_share WHERE segment_type = 'class'").fetchone()[0] or 1
    for g in groups:
        g["value_share"] = g.pop("w") / tot
    return {"kpis": cleanrows([k])[0], "classes": cleanrows(classes), "indexes": cleanrows(index),
            "movers": cleanrows(movers), "top_groups": cleanrows(groups)}


@router.get("/segments")
def segment(type: str = Query("class", pattern="^(class|molecule|combo)$"), id: str = Query(...), limit: int = 30):
    cur = db.cursor()
    return {"stats": cleanrows([db.one(cur, "SELECT * FROM segment_stats WHERE segment_type = ? AND segment = ?", [type, id]) or {}])[0],
            "share": cleanrows(share_table(cur, type, id, limit))}


@router.get("/concentration")
def concentration(type: str = Query("molecule", pattern="^(molecule|combo)$"), min_skus: int = 20,
                  order: str = "hhi_desc", page: int = 1, limit: int = Query(50, le=500)):
    """Which molecules/FDCs are monopolised vs fragmented — white-space finder for market entry."""
    cur = db.cursor()
    name = "m.name" if type == "molecule" else "k.label"
    join = ("JOIN molecules m ON CAST(m.id AS VARCHAR) = st.segment" if type == "molecule"
            else "JOIN combos k ON CAST(k.id AS VARCHAR) = st.segment")
    order_sql = {"hhi_desc": "st.hhi DESC", "hhi_asc": "st.hhi ASC", "skus": "st.skus DESC", "owners": "st.owners ASC"}.get(order, "st.hhi DESC")
    total = cur.execute(f"SELECT count(*) FROM segment_stats st WHERE segment_type = ? AND skus >= ?", [type, min_skus]).fetchone()[0]
    data = db.rows(cur, f"""
        SELECT st.segment AS id, {name} AS name, st.skus, st.owners, st.hhi, st.leader_share,
               coalesce(pa.name, co.name) AS leader
        FROM segment_stats st {join}
        LEFT JOIN parents pa ON st.leader LIKE 'parent:%' AND pa.id = CAST(split_part(st.leader, ':', 2) AS INT)
        LEFT JOIN companies co ON st.leader LIKE 'company:%' AND co.id = CAST(split_part(st.leader, ':', 2) AS INT)
        WHERE st.segment_type = ? AND st.skus >= ? ORDER BY {order_sql} LIMIT ? OFFSET ?""",
        [type, min_skus, limit, (page - 1) * limit])
    return paged(total, page, limit, data)


@router.get("/spreads")
def spreads(min_brands: int = 5, therapeutic_class: str | None = None, limit: int = Query(50, le=500), format: str = "json"):
    """Same composition, very different price: cheapest vs costliest brand and the Jan Aushadhi price."""
    cur = db.cursor()
    where, args = ["k.product_count >= ?", "k.min_mrp > 0"], [min_brands]
    if therapeutic_class:
        where.append("k.therapeutic_class = ?"); args.append(therapeutic_class)
    data = db.rows(cur, f"""
        SELECT k.id, k.label, k.therapeutic_class, k.product_count, k.company_count, k.min_mrp, k.median_mrp, k.max_mrp,
               round(k.max_mrp / k.min_mrp, 1) AS spread_x, k.banned_skus
        FROM combos k WHERE {' AND '.join(where)}
        ORDER BY k.product_count * ln(k.max_mrp / k.min_mrp) DESC LIMIT ?""", args + [limit])
    if format == "csv":
        return csv_response(data, "price_spreads")
    return {"data": cleanrows(data)}


@router.get("/launches")
def launches(limit: int = 60):
    """New to market: Jan Aushadhi additions, CDSCO approvals and NPPA new-drug price fixations, latest first."""
    cur = db.cursor()
    ev = db.rows(cur, """SELECT id, ts, kind, severity, title, url, source, entity_type, entity_id FROM events
                         WHERE kind IN ('launch', 'approval') OR (kind = 'price_notification' AND title ILIKE '%price calculation%')
                         ORDER BY ts DESC LIMIT ?""", [limit])
    newest_2025 = db.rows(cur, """SELECT p.id, p.name, p.mrp, c.name company, p.composition FROM products p
                                  LEFT JOIN companies c ON c.id = p.company_id
                                  WHERE p.sources = '1mg-2025' ORDER BY p.mrp DESC NULLS LAST LIMIT 40""")
    return {"events": cleanrows(ev), "catalog_new": cleanrows(newest_2025)}


@router.get("/classes")
def classes():
    cur = db.cursor()
    return {"data": [r[0] for r in cur.execute(
        "SELECT therapeutic_class FROM products WHERE therapeutic_class IS NOT NULL GROUP BY 1 ORDER BY count(*) DESC").fetchall()],
            "forms": [r[0] for r in cur.execute(
        "SELECT dosage_form FROM products WHERE dosage_form IS NOT NULL GROUP BY 1 HAVING count(*) > 50 ORDER BY count(*) DESC").fetchall()]}
