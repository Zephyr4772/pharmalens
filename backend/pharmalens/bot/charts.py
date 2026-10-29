"""Chart images for the Telegram bot (PNG bytes), drawn in the terminal's dark-amber style."""
import io
from datetime import date, timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

from .. import db  # noqa: E402

BG, PANEL, FG, DIM, AMBER, RED, GREEN = "#0b0f14", "#10161d", "#d5dce3", "#6b7785", "#e0a000", "#e5534b", "#3fb950"


def _fig(title: str, subtitle: str = ""):
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=130)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)
    for s in ax.spines.values():
        s.set_color("#222b35")
    ax.tick_params(colors=DIM, labelsize=8)
    ax.grid(True, color="#1c242d", linewidth=0.6)
    fig.text(0.07, 0.94, title, color=AMBER, fontsize=12, fontweight="bold", family="monospace")
    if subtitle:
        fig.text(0.07, 0.895, subtitle, color=DIM, fontsize=8, family="monospace")
    fig.subplots_adjust(top=0.84, bottom=0.12, left=0.08, right=0.97)
    return fig, ax


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG)
    plt.close(fig)
    return buf.getvalue()


def stock(ticker: str, label: str, days: int = 365) -> bytes | None:
    """Daily closes for an NSE ticker ('SUNPHARMA' or 'SUNPHARMA.NS'; indices like '^CNXPHARMA')."""
    t = ticker if ticker.startswith("^") or ticker.endswith(".NS") else f"{ticker}.NS"
    rows = db.cursor().execute("SELECT d, close FROM quote_history WHERE ticker = ? AND d >= ? ORDER BY d",
                               [t, date.today() - timedelta(days=days)]).fetchall()
    if len(rows) < 2:
        return None
    d, c = zip(*rows)
    chg = (c[-1] / c[0] - 1) * 100
    fig, ax = _fig(f"{label}  ₹{c[-1]:,.1f}", f"{t} · daily close · {days // 365 or 1}y · {chg:+.1f}% over the period")
    color = GREEN if chg >= 0 else RED
    ax.plot(d, c, color=color, linewidth=1.4)
    ax.fill_between(d, c, min(c), color=color, alpha=0.08)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    return _png(fig)


def nsq_monthly(label: str, company_ids: list[int] | None = None, months: int = 36) -> bytes | None:
    """Not-of-standard-quality and spurious batches per month, for some companies or the whole market."""
    where, args = "alert_month >= ?", [(date.today() - timedelta(days=31 * months)).strftime("%Y-%m")]
    if company_ids:
        where += f" AND company_id IN ({','.join('?' * len(company_ids))})"
        args += company_ids
    rows = db.cursor().execute(f"""SELECT alert_month, count(*) FILTER (WHERE category = 'NSQ'),
                                          count(*) FILTER (WHERE category = 'SPURIOUS')
                                   FROM reg_nsq WHERE {where} GROUP BY 1 ORDER BY 1""", args).fetchall()
    if not rows:
        return None
    # every month in the window, zeros included: a sparse record must look sparse
    have = {r[0]: r[1:] for r in rows}
    start = date.today().replace(day=1) - timedelta(days=31 * (months - 1))
    m, cur_m = [], start.replace(day=1)
    while cur_m <= date.today():
        m.append(cur_m.strftime("%Y-%m"))
        cur_m = (cur_m + timedelta(days=32)).replace(day=1)
    nsq = [have.get(k, (0, 0))[0] for k in m]
    sp = [have.get(k, (0, 0))[1] for k in m]
    fig, ax = _fig(f"{label}: failed batches", f"CDSCO NSQ + spurious lists · {sum(nsq):,} NSQ, {sum(sp):,} spurious since {m[0]}")
    x = range(len(m))
    ax.set_axisbelow(True)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.bar(x, nsq, color=AMBER, width=0.8, label="NSQ")
    ax.bar(x, sp, bottom=nsq, color=RED, width=0.8, label="spurious")
    step = max(1, len(m) // 12)
    ax.set_xticks(list(x)[::step], [s[2:] for s in m][::step])
    ax.legend(facecolor=PANEL, edgecolor="#222b35", labelcolor=FG, fontsize=8)
    return _png(fig)


def product_prices(pid: int) -> bytes | None:
    """Every MRP we have seen for a product, with where it came from."""
    cur = db.cursor()
    name = cur.execute("SELECT name FROM products WHERE id = ?", [pid]).fetchone()
    rows = cur.execute("SELECT observed_on, mrp, source FROM price_observations WHERE product_id = ? AND mrp > 0 ORDER BY observed_on",
                       [pid]).fetchall()
    if not name or not rows:
        return None
    d, p, s = zip(*rows)
    # observations carry no pack size: a jump can be a different pack (strip of 10 vs 15), not a price change
    fig, ax = _fig(f"{name[0][:48]}", f"MRP per pack as each source listed it · pack sizes can differ between sources · latest ₹{p[-1]:,.2f}")
    ax.step(d, p, where="post", color=AMBER, linewidth=1.6)
    ax.scatter(d, p, color=AMBER, s=22, zorder=3)
    for x, y, src in zip(d, p, s):
        ax.annotate(src.replace("mfr:", "")[:18], (x, y), textcoords="offset points", xytext=(4, 6), color=DIM, fontsize=7)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    lo, hi = min(p), max(p)
    ax.set_ylim(lo - (hi - lo or lo) * 0.3, hi + (hi - lo or hi) * 0.3)
    return _png(fig)


def fin_quarters(symbol: str, label: str, n: int = 8) -> bytes | None:
    """Quarterly revenue (bars) and net margin (line), consolidated results from NSE filings."""
    rows = db.cursor().execute("""SELECT period_end, revenue, net_profit FROM fin_results
                                  WHERE symbol = ? AND consolidated AND date_diff('day', period_start, period_end) < 100
                                  AND revenue IS NOT NULL ORDER BY period_end DESC LIMIT ?""", [symbol, n]).fetchall()[::-1]
    if len(rows) < 2:
        return None
    q = [f"{d:%b %y}" for d, _, _ in rows]
    rev = [r or 0 for _, r, _ in rows]
    margin = [(p / r * 100) if r and p is not None else None for _, r, p in rows]
    fig, ax = _fig(f"{label}: quarterly results", f"consolidated · revenue ₹ crore (bars) · net margin % (line) · latest {q[-1]}")
    x = range(len(q))
    ax.set_axisbelow(True)
    ax.bar(x, rev, color=AMBER, width=0.6)
    for i, v in enumerate(rev):
        ax.annotate(f"{v:,.0f}", (i, v), textcoords="offset points", xytext=(0, 3), ha="center", color=FG, fontsize=7)
    ax.set_xticks(list(x), q)
    ax2 = ax.twinx()
    ax2.plot(x, margin, color=GREEN, marker="o", linewidth=1.6)
    ax2.tick_params(colors=GREEN, labelsize=8)
    for s in ax2.spines.values():
        s.set_color("#222b35")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    fig.subplots_adjust(right=0.92)   # room for the margin axis on the right
    return _png(fig)
