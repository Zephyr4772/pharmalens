"""Investor views: the Today home (watchlist, ranked signals, results week, market) and the Companies screener.

Both read only what the feeds already store (quotes, NSE results and filings, NSQ lists, US FDA actions, events); the
screener is one row per listed group and is cached for a few minutes because it scans the whole catalogue once.
"""
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from ... import db
from ... import watchlist as wl
from ...bot.briefing import KIND_W, SEV_W
from ..common import cleanrows, csv_response

router = APIRouter(prefix="/invest", tags=["invest"])
_cache: dict[str, tuple[float, list[dict]]] = {}
TTL = 300


def qlabel(d) -> str | None:
    return f"Q{((d.month - 4) % 12) // 3 + 1} FY{(d.year + (1 if d.month > 3 else 0)) % 100:02d}" if d else None


COMPANIES_SQL = """
WITH listed AS (SELECT id, slug, name, ticker, ownership FROM parents WHERE ticker IS NOT NULL),
q AS (SELECT * FROM fin_results WHERE consolidated AND date_diff('day', period_start, period_end) < 100),
ranked AS (SELECT *, row_number() OVER (PARTITION BY symbol ORDER BY period_end DESC) rn FROM q),
latest AS (SELECT * FROM ranked WHERE rn = 1),
ttm AS (SELECT symbol, sum(eps) AS eps_ttm FROM ranked WHERE rn <= 4 GROUP BY 1
        HAVING count(eps) = 4 AND date_diff('day', min(period_start), max(period_end)) < 380),
fin AS (SELECT l.symbol, l.period_end, l.revenue, l.net_profit, l.filed_at,
               CASE WHEN l.revenue > 0 THEN l.net_profit / l.revenue * 100 END AS margin,
               CASE WHEN p.revenue > 0 AND l.revenue >= 0 THEN (l.revenue / p.revenue - 1) * 100 END AS rev_yoy,
               CASE WHEN p.net_profit > 0 AND l.net_profit > 0 THEN (l.net_profit / p.net_profit - 1) * 100 END AS profit_yoy,
               CASE WHEN p.revenue > 0 THEN p.net_profit / p.revenue * 100 END AS margin_prev
        FROM latest l LEFT JOIN q p ON p.symbol = l.symbol
             AND date_diff('day', p.period_end, l.period_end) BETWEEN 355 AND 375),
hist AS (SELECT ticker, arg_max(close, d) FILTER (WHERE d <= (SELECT max(d) FROM quote_history) - INTERVAL 365 DAY) AS close_1y
         FROM quote_history WHERE d >= (SELECT max(d) FROM quote_history) - INTERVAL 380 DAY GROUP BY 1),
nsq AS (SELECT c.parent_id,
               count(*) FILTER (WHERE n.alert_month >= strftime(current_date - INTERVAL 365 DAY, '%Y-%m')) AS nsq_12m,
               count(*) FILTER (WHERE n.alert_month >= strftime(current_date - INTERVAL 730 DAY, '%Y-%m')
                                  AND n.alert_month < strftime(current_date - INTERVAL 365 DAY, '%Y-%m')) AS nsq_prev,
               count(*) FILTER (WHERE n.alert_month >= strftime(current_date - INTERVAL 365 DAY, '%Y-%m') AND n.category = 'SPURIOUS') AS spurious_12m
        FROM reg_nsq n JOIN companies c ON c.id = n.company_id GROUP BY 1),
fda AS (SELECT parent_id,
               count(*) FILTER (WHERE kind = 'import_alert' AND issued_on >= current_date - INTERVAL 730 DAY) AS fda_alerts_2y,
               count(*) FILTER (WHERE kind = 'recall' AND issued_on >= current_date - INTERVAL 365 DAY) AS fda_recalls_1y
        FROM usfda_actions GROUP BY 1),
gov AS (SELECT parent_id,
               count(*) FILTER (WHERE topic = 'regulatory_action') AS reg_actions,
               count(*) FILTER (WHERE topic = 'litigation') AS litigation,
               count(*) FILTER (WHERE topic = 'mgmt_exit') AS mgmt_exits,
               count(*) FILTER (WHERE topic = 'mgmt_exit' AND regexp_matches(lower(text),
                                'chief financial|cfo|auditor|managing director|ceo|chief executive')) AS key_exits
        FROM corp_announcements WHERE announced_at >= now() - INTERVAL 365 DAY GROUP BY 1),
nxt AS (SELECT symbol, min(meeting_date) AS next_results FROM results_calendar
        WHERE meeting_date >= current_date AND regexp_matches(lower(description), 'result') GROUP BY 1)
SELECT l.id, l.slug, l.name, l.ticker, l.ownership,
       qt.price, qt.change_pct, qt.market_cap,
       coalesce(qt.pe, CASE WHEN ttm.eps_ttm > 0 THEN qt.price / ttm.eps_ttm END) AS pe, ttm.eps_ttm, qt.week52_high, qt.week52_low,
       CASE WHEN h.close_1y > 0 THEN (qt.price / h.close_1y - 1) * 100 END AS chg_1y,
       f.period_end, f.revenue, f.net_profit, f.margin, f.margin_prev, f.rev_yoy, f.profit_yoy, f.filed_at,
       coalesce(nsq.nsq_12m, 0) nsq_12m, coalesce(nsq.nsq_prev, 0) nsq_prev, coalesce(nsq.spurious_12m, 0) spurious_12m,
       coalesce(fda.fda_alerts_2y, 0) fda_alerts_2y, coalesce(fda.fda_recalls_1y, 0) fda_recalls_1y,
       coalesce(gov.reg_actions, 0) reg_actions, coalesce(gov.litigation, 0) litigation,
       coalesce(gov.mgmt_exits, 0) mgmt_exits, coalesce(gov.key_exits, 0) key_exits,
       nxt.next_results
FROM listed l
LEFT JOIN quotes qt ON qt.ticker = l.ticker || '.NS'
LEFT JOIN hist h ON h.ticker = l.ticker || '.NS'
LEFT JOIN fin f ON f.symbol = l.ticker
LEFT JOIN ttm ON ttm.symbol = l.ticker
LEFT JOIN nsq ON nsq.parent_id = l.id
LEFT JOIN fda ON fda.parent_id = l.id
LEFT JOIN gov ON gov.parent_id = l.id
LEFT JOIN nxt ON nxt.symbol = l.ticker
ORDER BY qt.market_cap DESC NULLS LAST
"""

DPCO_SQL = """
SELECT c.parent_id, count(*) AS skus,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM product_molecules pm JOIN molecules m ON m.id = pm.molecule_id
                                      WHERE pm.product_id = p.id AND m.nppa_ceiling IS NOT NULL)) AS dpco_skus
FROM products p JOIN companies c ON c.id = p.company_id
WHERE c.parent_id IN (SELECT id FROM parents WHERE ticker IS NOT NULL) AND NOT coalesce(p.is_discontinued, false)
GROUP BY 1
"""


def _n(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _flags(r: dict) -> list[dict]:
    """Same thresholds as Specs' /sanity, as short badges: level red | amber."""
    out = []
    if r["spurious_12m"] or r["nsq_12m"] >= 10:
        out.append({"level": "red", "label": "QUALITY", "why": f"{r['nsq_12m']} failed batches in 12m" + (f", {r['spurious_12m']} spurious" if r["spurious_12m"] else "")})
    elif r["nsq_12m"] >= 3:
        out.append({"level": "amber", "label": "QUALITY", "why": f"{r['nsq_12m']} failed batches in 12m"})
    if r["fda_alerts_2y"]:
        out.append({"level": "red", "label": "USFDA", "why": f"{_n(r['fda_alerts_2y'], 'import alert')} in 2y"})
    elif r["fda_recalls_1y"]:
        out.append({"level": "amber", "label": "USFDA", "why": f"{_n(r['fda_recalls_1y'], 'recall')} in 12m"})
    if r["reg_actions"] >= 3:
        out.append({"level": "red", "label": "ORDERS", "why": f"{_n(r['reg_actions'], 'regulatory action')} disclosed in 12m"})
    elif r["reg_actions"]:
        out.append({"level": "amber", "label": "ORDERS", "why": f"{_n(r['reg_actions'], 'regulatory action')} disclosed in 12m"})
    if r["litigation"]:
        out.append({"level": "amber", "label": "LEGAL", "why": f"{_n(r['litigation'], 'litigation disclosure')} in 12m"})
    if r["key_exits"]:
        out.append({"level": "red", "label": "MGMT", "why": f"{_n(r['key_exits'], 'CEO/CFO/MD/auditor exit')} in 12m"})
    elif r["mgmt_exits"] >= 3:
        out.append({"level": "amber", "label": "MGMT", "why": f"{r['mgmt_exits']} senior exits in 12m"})
    if (r["net_profit"] or 0) < 0 or (r["profit_yoy"] is not None and r["profit_yoy"] <= -30):
        out.append({"level": "red", "label": "PROFIT", "why": "loss or profit down 30%+ YoY in the latest quarter"})
    return out


def companies_rows() -> list[dict]:
    hit = _cache.get("companies")
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    cur = db.cursor()
    rows = db.rows(cur, COMPANIES_SQL)
    dpco = {p: (s, d) for p, s, d in cur.execute(DPCO_SQL).fetchall()}
    for r in rows:
        s, d = dpco.get(r["id"], (0, 0))
        r["skus"], r["dpco_share"] = s, (d / s * 100 if s else None)
        r["quarter"] = qlabel(r["period_end"])
        r["quality_trend"] = "rising" if r["nsq_12m"] > r["nsq_prev"] else "falling" if r["nsq_12m"] < r["nsq_prev"] else "flat"
        r["flags"] = _flags(r)
        r["risk"] = sum(2 if f["level"] == "red" else 1 for f in r["flags"])
    rows = cleanrows(rows)
    _cache["companies"] = (time.time(), rows)
    return rows


@router.get("/companies")
def companies(format: str | None = None):
    rows = companies_rows()
    if format == "csv":
        return csv_response([{k: v for k, v in r.items() if k != "flags"} | {"flags": " ".join(f["label"] for f in r["flags"])}
                             for r in rows], "pharmalens-companies")
    return {"data": rows, "asof": datetime.now().isoformat(timespec="seconds")}


# ------------------------------------------------------------------ Today
def _owner(request: Request) -> str | None:
    from .watchlist import _who
    try:
        return _who(request)
    except Exception:  # noqa: BLE001 — not signed in: Today still works, without the watchlist
        return None


def _watched(items: list[dict]) -> tuple[set[int], set[int]]:
    """Parent ids and company ids the watchlist covers (a watched company counts toward its group)."""
    cur = db.cursor()
    slugs_g = [i["key"][2:] for i in items if i["key"].startswith("g:")]
    slugs_c = [i["key"][3:] for i in items if i["key"].startswith("co:")]
    parents, comps = set(), set()
    if slugs_g:
        parents |= {r[0] for r in cur.execute(f"SELECT id FROM parents WHERE slug IN ({','.join('?' * len(slugs_g))})", slugs_g).fetchall()}
    if slugs_c:
        for cid, pid in cur.execute(f"SELECT id, parent_id FROM companies WHERE slug IN ({','.join('?' * len(slugs_c))})", slugs_c).fetchall():
            comps.add(cid)
            if pid:
                parents.add(pid)
    if parents:
        comps |= {r[0] for r in cur.execute(f"SELECT id FROM companies WHERE parent_id IN ({','.join(map(str, parents))})").fetchall()}
    return parents, comps


def _signals(watch_parents: set[int], watch_comps: set[int], days: int = 7, limit: int = 30) -> list[dict]:
    cur = db.cursor()
    rows = db.rows(cur, """
        SELECT e.id, e.ts, e.detected_at, e.kind, e.severity, e.title, e.source, e.url, e.entity_type, e.entity_id,
               coalesce(pa.id, pc.id) AS parent_id, coalesce(pa.name, pc.name) AS group_name, coalesce(pa.slug, pc.slug) AS group_slug,
               coalesce(pa.ticker, pc.ticker) AS ticker
        FROM events e
        LEFT JOIN parents pa ON e.entity_type = 'parent' AND pa.id = e.entity_id
        LEFT JOIN companies c ON e.entity_type = 'company' AND c.id = e.entity_id
        LEFT JOIN parents pc ON pc.id = c.parent_id
        WHERE e.detected_at >= now() - to_days(CAST(? AS INTEGER)) AND e.kind NOT IN ('news', 'stock')""", [days])
    now = datetime.now()
    for r in rows:
        age_h = max(0.0, (now - (r["detected_at"] or now)).total_seconds() / 3600)
        watched = (r["parent_id"] in watch_parents) or (r["entity_type"] == "company" and r["entity_id"] in watch_comps)
        r["watched"] = watched
        r["score"] = (SEV_W.get(r["severity"], 1) + KIND_W.get(r["kind"], 0) + (2 if r["ticker"] else 0)
                      + (5 if watched else 0) - age_h / 24)
    rows.sort(key=lambda r: -r["score"])
    # many NSQ batches from one maker read as one signal: keep the first two per (kind, group)
    seen: dict[tuple, int] = {}
    out = []
    for r in rows:
        k = (r["kind"], r["parent_id"] or r["title"][:40])
        seen[k] = seen.get(k, 0) + 1
        if seen[k] <= 2:
            out.append(r)
        if len(out) >= limit:
            break
    return cleanrows(out)


@router.get("/today")
def today(request: Request):
    cur = db.cursor()
    owner = _owner(request)
    items = wl.items(owner) if owner else []
    wp, wc = _watched(items)
    comp = {r["slug"]: r for r in companies_rows()}

    watch = []
    for it in items:
        row = {"key": it["key"], "label": it["label"], "href": it["href"]}
        typ, ref = it["key"].split(":", 1)
        slug = ref if typ == "g" else None
        if typ == "co":
            slug = (cur.execute("SELECT pa.slug FROM companies c JOIN parents pa ON pa.id = c.parent_id WHERE c.slug = ?", [ref]).fetchone() or [None])[0]
        g = comp.get(slug) if slug else None
        if g:
            row |= {k: g[k] for k in ("ticker", "price", "change_pct", "market_cap", "next_results", "quarter", "rev_yoy", "profit_yoy", "flags")}
            pid = g["id"]
            last = db.one(cur, """SELECT e.kind, e.severity, e.title, e.ts, e.url FROM events e
                                  LEFT JOIN companies c ON e.entity_type = 'company' AND c.id = e.entity_id
                                  WHERE ((e.entity_type = 'parent' AND e.entity_id = ?) OR c.parent_id = ?)
                                  AND e.kind <> 'stock' ORDER BY e.ts DESC LIMIT 1""", [pid, pid])
        else:
            et = {"m": "molecule", "c": "combo", "p": "product"}.get(typ)
            last = db.one(cur, "SELECT kind, severity, title, ts, url FROM events WHERE entity_type = ? AND entity_id = ? ORDER BY ts DESC LIMIT 1",
                          [et, int(ref)]) if et and ref.isdigit() else None
        row["last_event"] = cleanrows([last])[0] if last else None
        watch.append(row)

    week = db.rows(cur, """SELECT r.meeting_date, pa.name, pa.slug, pa.ticker, pa.id FROM results_calendar r JOIN parents pa ON pa.id = r.parent_id
                           WHERE r.meeting_date BETWEEN current_date AND current_date + INTERVAL 7 DAY
                           AND regexp_matches(lower(r.description), 'result')
                           GROUP BY ALL ORDER BY r.meeting_date, pa.name""")
    for r in week:
        r["watched"] = r.pop("id") in wp
    reported = [c for c in comp.values() if c["filed_at"] and (datetime.now() - datetime.fromisoformat(str(c["filed_at"]))).days <= 10]
    reported.sort(key=lambda c: str(c["filed_at"]), reverse=True)

    quotes = db.rows(cur, """SELECT q.ticker, q.name, q.price, q.change_pct, pa.slug, pa.name AS group_name FROM quotes q
                             LEFT JOIN parents pa ON pa.ticker || '.NS' = q.ticker WHERE q.price IS NOT NULL""")
    idx = [q for q in quotes if q["ticker"].startswith("^") or q["ticker"].startswith("NIFTY")]
    eq = sorted((q for q in quotes if q not in idx and q["change_pct"] is not None), key=lambda q: q["change_pct"])
    asof = cur.execute("SELECT max(quoted_at) FROM quotes").fetchone()[0]
    return {
        "signed_in": owner is not None,
        "watch": cleanrows(watch),
        "signals": _signals(wp, wc),
        "results_week": cleanrows(week),
        "reported": [{k: c[k] for k in ("slug", "name", "ticker", "quarter", "revenue", "net_profit", "margin", "rev_yoy", "profit_yoy", "filed_at", "change_pct")}
                     for c in reported[:12]],
        "market": {"indexes": cleanrows(idx), "gainers": cleanrows(eq[::-1][:5]), "losers": cleanrows(eq[:5]),
                   "breadth": [sum(1 for q in eq if q["change_pct"] > 0), sum(1 for q in eq if q["change_pct"] < 0)],
                   "asof": asof},
    }


# ------------------------------------------------------------------ company dossier (investor tabs)
def _group_row(pid: int) -> dict | None:
    """The screener's row for one group; built directly for unlisted groups, which the screener leaves out."""
    hit = next((r for r in companies_rows() if r["id"] == pid), None)
    if hit:
        return hit
    cur = db.cursor()
    rows = db.rows(cur, COMPANIES_SQL.replace("FROM parents WHERE ticker IS NOT NULL", "FROM parents WHERE id = ?"), [pid])
    if not rows:
        return None
    r = rows[0]
    _, s, d = cur.execute(DPCO_SQL.replace("(SELECT id FROM parents WHERE ticker IS NOT NULL)", "(?)"), [pid]).fetchone() or (pid, 0, 0)
    r["skus"], r["dpco_share"] = s, (d / s * 100 if s else None)
    r["quarter"] = qlabel(r["period_end"])
    r["quality_trend"] = "rising" if r["nsq_12m"] > r["nsq_prev"] else "falling" if r["nsq_12m"] < r["nsq_prev"] else "flat"
    r["flags"] = _flags(r)
    r["risk"] = sum(2 if f["level"] == "red" else 1 for f in r["flags"])
    return cleanrows([r])[0]


def _scorecard(r: dict, banned: int, listed: bool) -> list[dict]:
    """Every area with a level (red / amber / green / info) and the evidence, using /sanity's thresholds."""
    def lvl(red, amber):
        return "red" if red else "amber" if amber else "green"
    skus = r["skus"] or 0
    out = [
        {"area": "Quality (CDSCO NSQ)", "level": lvl(r["spurious_12m"] or r["nsq_12m"] >= 10, r["nsq_12m"] >= 3),
         "text": f"{r['nsq_12m']} failed-batch listings in 12 months ({r['quality_trend']}; {r['nsq_prev']} the year before)"
                 + (f", {r['spurious_12m']} spurious" if r["spurious_12m"] else "")},
        {"area": "US FDA", "level": lvl(r["fda_alerts_2y"], r["fda_recalls_1y"]),
         "text": f"{r['fda_alerts_2y']} import alerts in 2 years, {r['fda_recalls_1y']} recalls in 12 months"},
    ]
    if listed:
        out += [
            {"area": "Regulatory orders", "level": lvl(r["reg_actions"] >= 3, r["reg_actions"]),
             "text": f"{r['reg_actions']} actions / orders / penalties disclosed to NSE in 12 months"},
            {"area": "Litigation", "level": lvl(False, r["litigation"]), "text": f"{r['litigation']} litigation disclosures in 12 months"},
            {"area": "Management", "level": lvl(r["key_exits"], r["mgmt_exits"] >= 3),
             "text": f"{r['mgmt_exits']} senior exits in 12 months" + (f", incl. {r['key_exits']} CEO/CFO/MD/auditor" if r["key_exits"] else "")},
        ]
    else:
        out.append({"area": "Disclosures", "level": "info", "text": "unlisted: no exchange disclosures or published results to check"})
    out += [
        {"area": "Banned combinations", "level": lvl(False, skus and banned / skus > 0.01),
         "text": f"{banned} of {skus:,} active SKUs match a prohibited FDC"},
        {"area": "Price control (DPCO)", "level": "info",
         "text": f"{r['dpco_share']:.0f}% of active SKUs contain an NPPA ceiling-priced molecule" if r["dpco_share"] is not None else "no active SKUs on file"},
    ]
    if r["revenue"] is not None:
        loss = (r["net_profit"] or 0) < 0
        out.append({"area": f"Financials {r['quarter']}",
                    "level": lvl(loss or (r["profit_yoy"] is not None and r["profit_yoy"] <= -30), (r["rev_yoy"] or 0) < 0 or (r["profit_yoy"] or 0) < 0),
                    "text": f"revenue ₹{r['revenue']:,.0f} cr" + (f" ({r['rev_yoy']:+.0f}% YoY)" if r["rev_yoy"] is not None else "")
                            + f", net profit ₹{(r['net_profit'] or 0):,.0f} cr" + (f" ({r['profit_yoy']:+.0f}% YoY)" if r["profit_yoy"] is not None else "")})
    return out


def _peer_rank(rows: list[dict], me: dict, field: str, high_good: bool = True) -> dict | None:
    vals = sorted(r[field] for r in rows if r[field] is not None)
    if me.get(field) is None or not vals:
        return None
    better = sum(1 for v in vals if (v > me[field] if high_good else v < me[field]))
    return {"field": field, "value": me[field], "rank": better + 1, "of": len(vals), "median": vals[len(vals) // 2]}


def _with_yoy(rows: list[dict], quarterly: bool) -> list[dict]:
    for r in rows:
        prev = next((x for x in rows if 355 <= (r["period_end"] - x["period_end"]).days <= 375), None)
        for f in ("revenue", "net_profit", "eps"):
            a, b = r[f], (prev or {}).get(f)
            r[f"{f}_yoy"] = (a / b - 1) * 100 if a is not None and b and b > 0 and a >= 0 else None
        r["margin"] = r["net_profit"] / r["revenue"] * 100 if r["revenue"] and r["net_profit"] is not None else None
        # operating profit before interest, depreciation and other income (EBITDA as analysts usually quote it)
        r["ebitda"] = (r["pbt"] + (r["finance_costs"] or 0) + (r["depreciation"] or 0) - (r["other_income"] or 0)) if r["pbt"] is not None else None
        r["ebitda_margin"] = r["ebitda"] / r["revenue"] * 100 if r["ebitda"] is not None and r["revenue"] else None
        r["label"] = qlabel(r["period_end"]) if quarterly else f"FY{r['period_end'].year % 100:02d}"
    return rows


@router.get("/dossier/{slug}")
def dossier(slug: str):
    cur = db.cursor()
    p = db.one(cur, "SELECT id, slug, name, ticker FROM parents WHERE slug = ?", [slug])
    if not p:
        raise HTTPException(404, "unknown group")
    pid, sym = p["id"], p["ticker"]
    me = _group_row(pid)
    out: dict = {"listed": bool(sym)}

    if sym:
        q = db.rows(cur, """SELECT period_start, period_end, revenue, other_income, total_expenses, employee_cost, finance_costs,
                                   depreciation, pbt, tax, net_profit, profit_owners, eps, filed_at, source_url
                            FROM fin_results WHERE symbol = ? AND consolidated ORDER BY period_end DESC""", [sym])
        out["quarters"] = cleanrows(_with_yoy([r for r in q if (r["period_end"] - r["period_start"]).days < 100], True)[:12])
        out["annual"] = cleanrows(_with_yoy([r for r in q if 355 <= (r["period_end"] - r["period_start"]).days <= 375], False)[:5])
        out["calendar"] = cleanrows(db.rows(cur, """SELECT meeting_date, purpose, description FROM results_calendar WHERE symbol = ?
                                                    ORDER BY meeting_date DESC LIMIT 6""", [sym]))
        if me:
            allrows = companies_rows()
            out["peers"] = [x for x in (_peer_rank(allrows, me, "rev_yoy"), _peer_rank(allrows, me, "profit_yoy"),
                                        _peer_rank(allrows, me, "margin"), _peer_rank(allrows, me, "pe", high_good=False),
                                        _peer_rank(allrows, me, "chg_1y"), _peer_rank(allrows, me, "market_cap")) if x]

    banned = cur.execute("""SELECT count(*) FROM products p JOIN companies c ON c.id = p.company_id
                            WHERE c.parent_id = ? AND p.ban_level = 'exact' AND NOT coalesce(p.is_discontinued, false)""", [pid]).fetchone()[0]
    if me:
        out["metrics"] = {k: me[k] for k in ("pe", "eps_ttm", "chg_1y", "rev_yoy", "profit_yoy", "margin", "quarter", "next_results", "risk", "flags")}
        out["scorecard"] = _scorecard(me, banned, bool(sym))
    out["nsq_quarterly"] = cleanrows(db.rows(cur, """
        SELECT strftime(date_trunc('quarter', strptime(alert_month || '-01', '%Y-%m-%d')), '%Y-%m') AS q,
               count(*) AS n, count(*) FILTER (WHERE category = 'SPURIOUS') AS spurious
        FROM reg_nsq n JOIN companies c ON c.id = n.company_id
        WHERE c.parent_id = ? AND alert_month >= strftime(current_date - INTERVAL 3 YEAR, '%Y-%m') GROUP BY 1 ORDER BY 1""", [pid]))
    out["disclosures"] = cleanrows(db.rows(cur, """SELECT announced_at, topic, text, attachment FROM corp_announcements WHERE parent_id = ?
                                                   AND topic IN ('regulatory_action', 'litigation', 'mgmt_exit', 'credit', 'usfda', 'plant')
                                                   AND announced_at >= now() - INTERVAL 730 DAY ORDER BY announced_at DESC LIMIT 60""", [pid]))
    ev = """SELECT e.id, e.ts, e.kind, e.severity, e.title, e.url, e.source FROM events e
            LEFT JOIN companies c ON e.entity_type = 'company' AND c.id = e.entity_id
            WHERE ((e.entity_type = 'parent' AND e.entity_id = ?) OR c.parent_id = ?) AND e.kind {} ORDER BY e.ts DESC LIMIT ?"""
    tl = {r["id"]: r for r in db.rows(cur, ev.format("<> 'stock'"), [pid, pid, 60])}
    try:   # events linked to this group through event_entities (Phase 1 #9): high-confidence only
        for r in db.rows(cur, """SELECT e.id, e.ts, e.kind, e.severity, e.title, e.url, e.source FROM event_entities x JOIN events e ON e.id = x.event_id
                                 WHERE x.entity_type = 'parent' AND x.entity_id = ? AND x.confidence >= 0.85 AND e.kind <> 'stock'
                                 ORDER BY e.ts DESC LIMIT 60""", [str(pid)]):
            tl.setdefault(r["id"], r)
    except Exception:  # noqa: BLE001 — before the first linker run
        pass
    out["timeline"] = cleanrows(sorted(tl.values(), key=lambda r: str(r["ts"]), reverse=True)[:60])
    out["approvals"] = cleanrows(db.rows(cur, ev.format("IN ('approval', 'trial', 'launch', 'usfda')"), [pid, pid, 40]))
    return out
