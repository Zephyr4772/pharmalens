"""Listed Indian pharma equities via Yahoo Finance (NSE, ~15 min delayed)."""
import math
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import yfinance as yf

from .. import db
from .base import Connector

IST = ZoneInfo("Asia/Kolkata")
INDEXES = {"^CNXPHARMA": "Nifty Pharma", "^NSEI": "Nifty 50", "NIFTY_HEALTHCARE.NS": "Nifty Healthcare"}


def market_open(now: datetime | None = None) -> bool:
    now = now or datetime.now(IST)
    return now.weekday() < 5 and dtime(9, 10) <= now.time() <= dtime(15, 40)


def fnum(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


class NseQuotes(Connector):
    name = "nse_quotes"
    title = "NSE Pharma Equities"
    agency = "NSE (via Yahoo Finance)"
    schedule = {"trigger": "interval", "minutes": 5}
    description = "Last price, change, volume for listed pharma groups and the Nifty Pharma index (15-min delayed)."

    def tickers(self) -> dict[str, str]:
        rows = db.cursor().execute("SELECT ticker, name FROM parents WHERE ticker IS NOT NULL").fetchall()
        out = {f"{t}.NS": n for t, n in rows}
        out.update(INDEXES)
        return out

    def run(self):
        have = db.cursor().execute("SELECT count(*) FROM quotes").fetchone()[0]
        if have and not market_open():
            self.stats.notes.append("market closed")
            return
        tk = self.tickers()
        hist = yf.download(list(tk), period="5d", interval="1d", progress=False, auto_adjust=False, group_by="ticker", threads=True)
        now = datetime.now()
        with db.writer() as cur:
            for sym, name in tk.items():
                try:
                    h = hist[sym].dropna(subset=["Close"])
                except KeyError:
                    continue
                if h.empty:
                    continue
                last = h.iloc[-1]
                prev = h.iloc[-2]["Close"] if len(h) > 1 else None
                price = fnum(last["Close"])
                chg = (price / fnum(prev) - 1) * 100 if price and fnum(prev) else None
                cur.execute(
                    """INSERT OR REPLACE INTO quotes (ticker, name, price, prev_close, change_pct, day_high, day_low, volume, currency, quoted_at,
                       market_cap, pe, week52_high, week52_low)
                       VALUES (?,?,?,?,?,?,?,?, 'INR', ?,
                               (SELECT market_cap FROM quotes WHERE ticker = ?), (SELECT pe FROM quotes WHERE ticker = ?),
                               (SELECT week52_high FROM quotes WHERE ticker = ?), (SELECT week52_low FROM quotes WHERE ticker = ?))""",
                    [sym, name, price, fnum(prev), chg, fnum(last["High"]), fnum(last["Low"]), fnum(last["Volume"]), now, sym, sym, sym, sym],
                )
                for d, row in h.iterrows():
                    cur.execute("INSERT OR REPLACE INTO quote_history VALUES (?,?,?,?)", [sym, d.date(), fnum(row["Close"]), fnum(row["Volume"])])
                self.stats.rows_seen += 1
                if chg is not None and abs(chg) >= 5 and not sym.startswith("^"):
                    pid = cur.execute("SELECT id FROM parents WHERE ticker = ?", [sym[:-3]]).fetchone()
                    self.emit(cur, kind="stock", severity="high" if abs(chg) >= 8 else "medium",
                              title=f"{name} {'▲' if chg > 0 else '▼'} {chg:+.1f}% at ₹{price:,.1f}",
                              entity_type="parent" if pid else None, entity_id=pid[0] if pid else None,
                              dedupe_key=f"move|{sym}|{h.index[-1].date()}|{int(chg)}")


class NseFundamentals(Connector):
    name = "nse_fundamentals"
    title = "NSE Pharma Fundamentals & 1Y History"
    agency = "NSE (via Yahoo Finance)"
    schedule = {"trigger": "cron", "hour": 18, "minute": 30}
    description = "Market cap, P/E, 52-week range and one year of daily closes for each listed group."

    def run(self):
        tk = NseQuotes().tickers()
        hist = yf.download(list(tk), period="1y", interval="1d", progress=False, auto_adjust=False, group_by="ticker", threads=True)
        info = {}
        for sym in tk:
            if sym.startswith("^") or sym.startswith("NIFTY"):
                continue
            try:
                fi = yf.Ticker(sym).fast_info
                info[sym] = (fnum(fi.get("marketCap")), fnum(fi.get("yearHigh")), fnum(fi.get("yearLow")))
            except Exception:  # noqa: BLE001
                continue
        with db.writer() as cur:
            for sym, name in tk.items():
                try:
                    h = hist[sym].dropna(subset=["Close"])
                except KeyError:
                    continue
                for d, row in h.iterrows():
                    cur.execute("INSERT OR REPLACE INTO quote_history VALUES (?,?,?,?)", [sym, d.date(), fnum(row["Close"]), fnum(row["Volume"])])
                self.stats.rows_seen += len(h)
                if not len(h):
                    continue
                mc, hi, lo = info.get(sym, (None, None, None))
                if hi is None:
                    hi, lo = fnum(h["High"].max()), fnum(h["Low"].min())
                last, prev = fnum(h.iloc[-1]["Close"]), (fnum(h.iloc[-2]["Close"]) if len(h) > 1 else None)
                cur.execute(
                    """INSERT INTO quotes (ticker, name, price, prev_close, change_pct, market_cap, week52_high, week52_low, currency, quoted_at)
                       VALUES (?,?,?,?,?,?,?,?, 'INR', now())
                       ON CONFLICT (ticker) DO UPDATE SET market_cap = excluded.market_cap, week52_high = excluded.week52_high,
                       week52_low = excluded.week52_low, name = excluded.name""",
                    [sym, name, last, prev, ((last / prev - 1) * 100) if last and prev else None, mc, hi, lo],
                )
