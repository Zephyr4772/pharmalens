"""Specs' results desk: a preview on the morning a company reports, a summary once the numbers are filed, and a
weekly digest of the watchlist and the sector.

Facts only from the database (NSE results and board meetings, quotes, filings, the screener rows); the wording is a
fixed template so these always go out, even with no model reachable. Watched groups get the full treatment; the rest
are batched into one line each so the chat is not flooded in results season.
"""
from datetime import date, datetime, timedelta

from .. import db
from .. import watchlist as wl
from .commands import Reply, cb, link, qlabel


def _rows() -> dict[int, dict]:
    from ..api.routers.invest import companies_rows
    return {r["id"]: r for r in companies_rows()}


def watched_groups() -> set[int]:
    """Groups on the owner's watchlist (a watched company counts toward its group)."""
    from ..api.routers.invest import _watched
    return _watched(wl.items(wl.owner_login()))[0]


def _quarters(symbol: str) -> list[dict]:
    return db.rows(db.cursor(), """SELECT period_start, period_end, revenue, net_profit, eps, filed_at FROM fin_results
                                   WHERE symbol = ? AND consolidated AND date_diff('day', period_start, period_end) < 100
                                   ORDER BY period_end DESC LIMIT 9""", [symbol])


def _year_ago(rows: list[dict], end: date) -> dict | None:
    return next((r for r in rows if 355 <= (end - r["period_end"]).days <= 375), None)


def _margin(r: dict | None) -> float | None:
    return r["net_profit"] / r["revenue"] * 100 if r and r.get("revenue") and r.get("net_profit") is not None else None


def _chg(a, b) -> str:
    return f"{(a / b - 1) * 100:+.0f}%" if a is not None and b and b > 0 and a >= 0 else "n/a"


def _cr(x) -> str:
    return "n/a" if x is None else f"₹{x:,.0f} cr" if x >= 0 else f"-₹{-x:,.0f} cr"


def _stock(g: dict) -> str:
    bits = []
    if g.get("price"):
        bits.append(f"₹{g['price']:,.0f}" + (f" ({g['change_pct']:+.1f}% today)" if g.get("change_pct") is not None else ""))
    if g.get("chg_1y") is not None:
        bits.append(f"1Y {g['chg_1y']:+.0f}%")
    if g.get("pe"):
        bits.append(f"P/E {g['pe']:.0f}")
    return " · ".join(bits)


def _buttons(g: dict) -> list[list[tuple[str, str]]]:
    return [[cb("Results chart", f"chart:f:{g['ticker']}"), cb("Sanity check", f"sanity:{g['id']}")],
            [link("Financials in terminal", f"/g/{g['slug']}?tab=fin")]]


# ------------------------------------------------------------------ preview (morning of the board meeting)
def preview(pid: int, meeting: date | None = None) -> Reply | None:
    g = _rows().get(pid)
    if not g:
        return None
    q = _quarters(g["ticker"])
    lines = [f"**Results day: {g['name']}** ({g['ticker']})" + (f", board meets {meeting:%a %d %b}" if meeting else "")]
    if q:
        last = q[0]
        target_end = last["period_end"] + timedelta(days=92)
        base = _year_ago(q, target_end)
        prev_yoy = _year_ago(q, last["period_end"])
        lines.append(f"Last quarter {qlabel(last['period_end'])}: revenue {_cr(last['revenue'])} ({_chg(last['revenue'], (prev_yoy or {}).get('revenue'))} YoY), "
                     f"profit {_cr(last['net_profit'])} ({_chg(last['net_profit'], (prev_yoy or {}).get('net_profit'))}), "
                     f"margin {_margin(last) or 0:.1f}%")
        if base:
            lines.append(f"Bar to clear ({qlabel(target_end)} vs {qlabel(base['period_end'])}): revenue {_cr(base['revenue'])}, "
                         f"profit {_cr(base['net_profit'])}, margin {_margin(base) or 0:.1f}%. Growth means beating these.")
        ms = [m for m in (_margin(r) for r in q[:4][::-1]) if m is not None]
        if len(ms) >= 3:
            lines.append("Net margin, last 4 quarters: " + " → ".join(f"{m:.1f}%" for m in ms)
                         + (" (improving)" if ms[-1] > ms[0] + 1 else " (slipping)" if ms[-1] < ms[0] - 1 else " (steady)"))
    else:
        lines.append("No earlier results on file in the integrated format, so no baseline.")
    if s := _stock(g):
        lines.append(f"Stock: {s}")
    if g["flags"]:
        lines.append("Open flags: " + "; ".join(f["why"] for f in g["flags"]))
    lines.append("_No analyst consensus here: the comparison is against its own history._")
    return Reply("\n".join(lines), _buttons(g))


def previews_for(day: date) -> list[Reply]:
    """Full previews for watched groups reporting that day, one line listing everyone else."""
    cur = db.cursor()
    meet = cur.execute("""SELECT DISTINCT parent_id FROM results_calendar WHERE meeting_date = ? AND parent_id IS NOT NULL
                          AND regexp_matches(lower(description), 'result')""", [day]).fetchall()
    ids = [r[0] for r in meet]
    if not ids:
        return []
    rows, watched = _rows(), watched_groups()
    out = [p for pid in ids if pid in watched and (p := preview(pid, day))]
    others = sorted((rows[i] for i in ids if i not in watched and i in rows), key=lambda r: -(r["market_cap"] or 0))
    if others:
        out.append(Reply(f"**Also reporting {day:%a %d %b}:** " + ", ".join(r["name"] for r in others)
                         + "\nSend /preview <name> for any of them, or /watch it to get these automatically.",
                         [[cb("Results calendar", "results:")]]))
    return out


# ------------------------------------------------------------------ summary (once the numbers are filed)
def summary(symbol: str, period_end: date) -> tuple[Reply, bool] | None:
    """(reply, is_watched)."""
    g = next((r for r in _rows().values() if r["ticker"] == symbol), None)
    if not g:
        return None
    q = _quarters(symbol)
    cur_q = next((r for r in q if r["period_end"] == period_end), None)
    if not cur_q:
        return None
    base = _year_ago(q, period_end)
    prev = next((r for r in q if 80 <= (period_end - r["period_end"]).days <= 100), None)
    m, mb = _margin(cur_q), _margin(base)
    ry = (cur_q["revenue"] / base["revenue"] - 1) * 100 if base and base["revenue"] else None
    py = (cur_q["net_profit"] / base["net_profit"] - 1) * 100 if base and base["net_profit"] and base["net_profit"] > 0 and (cur_q["net_profit"] or 0) >= 0 else None
    verdict = ("loss" if (cur_q["net_profit"] or 0) < 0 else
               "strong" if ry is not None and py is not None and ry > 10 and py > 10 else
               "weak" if (ry is not None and ry < 0) or (py is not None and py < -10) else "mixed" if ry is not None else "in")
    head = {"loss": "🔴 a loss", "strong": "🟢 strong", "weak": "🔴 weak", "mixed": "🟠 mixed", "in": "results in"}[verdict]
    lines = [f"**{g['name']} {qlabel(period_end)}: {head}**",
             f"Revenue {_cr(cur_q['revenue'])} ({_chg(cur_q['revenue'], (base or {}).get('revenue'))} YoY, "
             f"{_chg(cur_q['revenue'], (prev or {}).get('revenue'))} QoQ)",
             f"Net profit {_cr(cur_q['net_profit'])} ({_chg(cur_q['net_profit'], (base or {}).get('net_profit'))} YoY)"
             + (f", EPS ₹{cur_q['eps']:.2f}" if cur_q.get("eps") is not None else "")]
    if m is not None:
        lines.append(f"Net margin {m:.1f}%" + (f" vs {mb:.1f}% a year ago ({m - mb:+.1f} pts)" if mb is not None else ""))
    # against the other listed groups that have reported the same quarter so far
    season = db.rows(db.cursor(), """SELECT f.symbol, f.revenue, b.revenue AS base FROM fin_results f
                                     JOIN fin_results b ON b.symbol = f.symbol AND b.consolidated
                                       AND date_diff('day', b.period_start, b.period_end) < 100
                                       AND date_diff('day', b.period_end, f.period_end) BETWEEN 355 AND 375
                                     WHERE f.consolidated AND f.period_end = ? AND b.revenue > 0
                                       AND date_diff('day', f.period_start, f.period_end) < 100""", [period_end])
    if ry is not None and len(season) >= 4:
        growth = sorted((r["revenue"] / r["base"] - 1) * 100 for r in season)
        rank = sum(1 for x in growth if x > ry) + 1
        lines.append(f"Season so far: #{rank} of {len(growth)} on revenue growth (median {growth[len(growth) // 2]:+.0f}%)")
    if s := _stock(g):
        lines.append(f"Stock: {s}")
    return Reply("\n".join(lines), _buttons(g)), g["id"] in watched_groups()


def batch_line(symbol: str, period_end: date) -> str | None:
    q = _quarters(symbol)
    r = next((x for x in q if x["period_end"] == period_end), None)
    if not r:
        return None
    base = _year_ago(q, period_end)
    name = (db.cursor().execute("SELECT name FROM parents WHERE ticker = ?", [symbol]).fetchone() or [symbol])[0]
    return (f"- {name}: revenue {_cr(r['revenue'])} ({_chg(r['revenue'], (base or {}).get('revenue'))}), "
            f"profit {_cr(r['net_profit'])} ({_chg(r['net_profit'], (base or {}).get('net_profit'))})")


# ------------------------------------------------------------------ weekly digest
def weekly(end: datetime | None = None) -> Reply:
    end = end or datetime.now()
    start = end - timedelta(days=7)
    cur = db.cursor()
    rows, watched = _rows(), watched_groups()
    lines = [f"**Weekly digest** ({start:%d %b} to {end:%d %b})"]

    def wk(ticker: str) -> float | None:
        r = cur.execute("""SELECT arg_max(h.close, h.d) FILTER (WHERE h.d <= ?), coalesce(any_value(q.price), arg_max(h.close, h.d))
                           FROM quote_history h LEFT JOIN quotes q ON q.ticker = h.ticker
                           WHERE h.ticker = ? AND h.d >= ? - INTERVAL 14 DAY""", [start.date(), ticker, start.date()]).fetchone()
        return (r[1] / r[0] - 1) * 100 if r and r[0] and r[1] else None   # live quote against the close a week ago

    np_, n50 = wk("^CNXPHARMA"), wk("^NSEI")
    if np_ is not None:
        lines.append(f"Nifty Pharma {np_:+.1f}% on the week" + (f" vs Nifty 50 {n50:+.1f}%" if n50 is not None else ""))

    if watched:
        lines += ["", "**Your watchlist**"]
        for pid in sorted(watched, key=lambda i: -(rows.get(i, {}).get("market_cap") or 0)):
            g = rows.get(pid)
            if not g:
                name = (cur.execute("SELECT name FROM parents WHERE id = ?", [pid]).fetchone() or ["?"])[0]
                lines.append(f"- {name}: unlisted")
                continue
            w = wk(f"{g['ticker']}.NS")
            ev = cur.execute("""SELECT count(*) FROM events e LEFT JOIN companies c ON e.entity_type = 'company' AND c.id = e.entity_id
                                WHERE ((e.entity_type = 'parent' AND e.entity_id = ?) OR c.parent_id = ?) AND e.kind NOT IN ('stock', 'news')
                                AND e.detected_at >= ?""", [pid, pid, start]).fetchone()[0]
            lines.append(f"- {g['name']}: " + (f"{w:+.1f}% week" if w is not None else "no price")
                         + (f", {ev} signals" if ev else "") + (f", results {g['next_results']}" if g.get("next_results") else "")
                         + (" ⚠ " + ", ".join(f["label"].lower() for f in g["flags"] if f["level"] == "red") if any(f["level"] == "red" for f in g["flags"]) else ""))
    else:
        lines.append("Watchlist empty: /watch a few names and this digest gets personal.")

    rep = db.rows(cur, """SELECT f.symbol, pa.name, f.period_end, f.revenue, f.net_profit, b.revenue AS br, b.net_profit AS bp FROM fin_results f
                          JOIN parents pa ON pa.ticker = f.symbol
                          LEFT JOIN fin_results b ON b.symbol = f.symbol AND b.consolidated AND date_diff('day', b.period_start, b.period_end) < 100
                            AND date_diff('day', b.period_end, f.period_end) BETWEEN 355 AND 375
                          WHERE f.consolidated AND date_diff('day', f.period_start, f.period_end) < 100 AND f.filed_at >= ?""", [start])
    if rep:
        g_ = [(r, (r["revenue"] / r["br"] - 1) * 100) for r in rep if r["br"]]
        g_.sort(key=lambda x: -x[1])
        lines += ["", f"**Results this week**: {len(rep)} groups reported"]
        if g_:
            lines.append(f"Median revenue growth {g_[len(g_) // 2][1]:+.0f}% YoY")
            lines.append("Fastest: " + ", ".join(f"{r['name']} {x:+.0f}%" for r, x in g_[:3]))
            if len(g_) > 3:
                lines.append("Slowest: " + ", ".join(f"{r['name']} {x:+.0f}%" for r, x in g_[-3:][::-1]))
        losses = [r["name"] for r in rep if (r["net_profit"] or 0) < 0]
        if losses:
            lines.append("Losses: " + ", ".join(losses))

    flags = cur.execute("""SELECT pa.name, a.topic, count(*) FROM corp_announcements a JOIN parents pa ON pa.id = a.parent_id
                           WHERE a.announced_at >= ? AND a.topic IN ('regulatory_action', 'litigation', 'mgmt_exit')
                           GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 6""", [start]).fetchall()
    if flags:
        lab = {"regulatory_action": "regulatory order", "litigation": "litigation", "mgmt_exit": "senior exit"}
        lines += ["", "**New governance flags**"] + [f"- {n}: {c} {lab[t]}{'s' if c > 1 else ''}" for n, t, c in flags]

    nxt = cur.execute("""SELECT r.meeting_date, pa.id, pa.name FROM results_calendar r JOIN parents pa ON pa.id = r.parent_id
                         WHERE r.meeting_date BETWEEN ? AND ? AND regexp_matches(lower(r.description), 'result')
                         GROUP BY ALL ORDER BY 1, 3""", [end.date() + timedelta(days=1), end.date() + timedelta(days=8)]).fetchall()
    if nxt:
        lines += ["", "**Reporting next week**"]
        by_day: dict = {}
        for d, pid, n in nxt:
            by_day.setdefault(d, []).append(f"**{n}**" if pid in watched else n)
        lines += [f"- {d:%a %d %b}: {', '.join(ns)}" for d, ns in by_day.items()]
    return Reply("\n".join(lines), [[cb("Results calendar", "results:"), link("Today in terminal", "/")]])
