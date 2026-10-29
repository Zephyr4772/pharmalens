"""Slash commands and button actions for the Telegram bot.

Each handler returns a list of Reply objects (text, buttons, a chart image or a file). Button callbacks carry short
strings (Telegram allows 64 bytes): "<action>:<arg>". Free text that is not a command goes to the Specs agent.
"""
import csv
import io
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .. import db
from ..config import DATA_DIR, DB_PATH
from . import briefing, charts

TERMINAL = os.getenv("DRUGDEN_TERMINAL_URL", "https://srv1.tailf3b6bc.ts.net")
STARTED = time.time()


@dataclass
class Reply:
    text: str = ""
    buttons: list[list[tuple[str, str]]] = field(default_factory=list)   # (label, "cb:<data>" | "url:<https>")
    photo: bytes | None = None
    document: tuple[str, bytes] | None = None


def cb(label: str, data: str) -> tuple[str, str]:
    return (label, f"cb:{data[:64]}")


def link(label: str, path: str) -> tuple[str, str]:
    return (label, f"url:{TERMINAL}{path}")


def inr(x) -> str:
    return "—" if x is None else f"₹{x:,.2f}".rstrip("0").rstrip(".") if x < 100 else f"₹{x:,.0f}"


# ------------------------------------------------------------------ /help
COMMANDS = [
    ("brief", "briefing now: what happened and why it matters"),
    ("check", "check a medicine: bans, failed batches, price, cheaper options"),
    ("company", "company snapshot: quality, US FDA, news, share price"),
    ("chart", "chart a stock, a company's quality record or a product's prices"),
    ("export", "answer a question as a CSV file"),
    ("feeds", "data feed health, with run buttons"),
    ("status", "server health"),
    ("reset", "clear the conversation"),
]


def help_(_: str = "") -> list[Reply]:
    lines = ["**Specs.** I run the pipes. Commands, or just ask me anything:"]
    lines += [f"/{c}: {d}" for c, d in COMMANDS]
    lines.append("\nExamples: `/check dolo 650` · `/company cipla` · `/chart sunpharma` · `/chart nsq` · "
                 "`/export top 50 companies by NSQ batches in 2026`")
    return [Reply("\n".join(lines), [[cb("Brief me", "brief"), cb("Feeds", "feeds"), link("Terminal", "/")]])]


# ------------------------------------------------------------------ /check
def check(arg: str) -> list[Reply]:
    arg = arg.strip()
    if not arg:
        return [Reply("Which medicine? e.g. `/check dolo 650`")]
    from ..api.routers.catalog import search
    if arg.isdigit():
        return product_card(int(arg))
    hits = (search(q=arg, limit=6) or {}).get("products") or []
    if not hits:
        return [Reply(f"Nothing called '{arg}' in the catalog. Try the brand as printed on the strip.")]
    exact = [h for h in hits if h["name"].lower().startswith(arg.lower())]
    if len(hits) == 1 or len(exact) == 1:
        return product_card((exact or hits)[0]["id"])
    # 'dolo 650' -> 'Dolo 650 Tablet' over 'Dolo 650Mg Tablet 15 S': the shortest exact name with a known maker
    named = sorted((h for h in exact if h.get("company")), key=lambda h: len(h["name"]))
    if named and len(named[0]["name"]) <= len(arg) + 12:
        cards = product_card(named[0]["id"])
        others = [h for h in hits if h["id"] != named[0]["id"]][:4]
        if others:
            cards.append(Reply("Other matches:", [[cb(f"{h['name'][:40]} · {h.get('company') or ''}"[:60], f"check:{h['id']}")] for h in others]))
        return cards
    return [Reply(f"Several matches for '{arg}'. Which one?",
                  [[cb(f"{h['name'][:40]} · {h.get('company') or ''}"[:60], f"check:{h['id']}")] for h in hits])]


def product_card(pid: int) -> list[Reply]:
    from ..api.routers.catalog import product
    try:
        d = product(pid)
    except Exception:  # noqa: BLE001 — 404 for a stale button
        return [Reply("That product is no longer in the catalog.")]
    asof = (d.get("mrp_asof") or "").replace("mfr ", "manufacturer list ")
    lines = [f"**{d['name']}**", f"{d.get('company') or '—'}" + (f" · {d['parent']} group" if d.get("parent") else "")]
    lines.append(f"MRP {inr(d.get('mrp'))} for {d.get('pack_size') or 'pack'}"
                 + (f" · ₹{d['unit_price']:.2f}/unit" if d.get("unit_price") else "") + (f" · as of {asof}" if asof else ""))
    if d.get("ban_level") == "exact":
        lines.append(f"🔴 **Prohibited FDC**: {d['ban'][0]['combo_text'][:120]} ({d['ban'][0]['notification']})" if d.get("ban") else "🔴 **Prohibited FDC**")
    elif d.get("ban_level") == "review":
        lines.append("🟠 Same molecules as a banned combination: check strength and form on the pack")
    else:
        lines.append("✅ Not on the prohibited-FDC lists")
    nsq_maker, nsq_mol = len(d.get("nsq_same_maker") or []), d.get("nsq_same_molecule") or 0
    lines.append(f"Quality: maker has {nsq_maker}{'+' if nsq_maker >= 20 else ''} failed-batch listings; "
                 f"{nsq_mol:,} industry-wide for these molecules")
    eq = d.get("equivalents") or []
    if eq and eq[0].get("unit_price") and d.get("unit_price"):
        save = (1 - eq[0]["unit_price"] / d["unit_price"]) * 100
        lines.append(f"Cheapest same-composition: {eq[0]['name']} at ₹{eq[0]['unit_price']:.2f}/unit"
                     + (f" ({save:.0f}% less)" if save > 1 else ""))
    ja = (d.get("jan_aushadhi") or [None])[0]
    if ja:
        lines.append(f"Jan Aushadhi generic: {inr(ja.get('mrp'))} ({ja.get('unit_size')})")
    m = d.get("mfr_price")
    if m:
        lines.append(f"Manufacturer list ({m['effective_on']}): MRP {inr(m['mrp'])}"
                     + (f", PTR {inr(m['ptr'])}" if m.get("ptr") else ""))
    nn = (d.get("nppa_notified") or [None])[0]
    if nn and nn.get("same_company"):
        lines.append(f"NPPA notified launch price: ₹{nn['price']:g} per {nn['unit']} ({nn['notified_on']})")
    buttons = [[cb("Price history", f"chart:p:{pid}"), cb("Cheaper options", f"cheap:{pid}")],
               [link("Open in terminal", f"/p/{pid}")]]
    return [Reply("\n".join(lines), buttons)]


def cheap(pid: str) -> list[Reply]:
    from ..api.routers.catalog import product
    d = product(int(pid))
    eq = [e for e in (d.get("equivalents") or []) if e.get("unit_price")][:10]
    if not eq:
        return [Reply("No priced same-composition alternatives in the catalog.")]
    lines = [f"**Same composition as {d['name']}**, cheapest first (per unit):"]
    lines += [f"- {e['name']} · {e.get('company') or '—'} · ₹{e['unit_price']:.2f}" for e in eq]
    return [Reply("\n".join(lines), [[cb(f"Check {e['name'][:22]}", f"check:{e['id']}")] for e in eq[:3]])]


# ------------------------------------------------------------------ /company
def _find_group(arg: str):
    cur = db.cursor()
    q = arg.strip()
    row = db.one(cur, """SELECT pa.id, pa.slug, pa.name, pa.ticker FROM parents pa
                         LEFT JOIN (SELECT parent_id, sum(product_count) n FROM companies GROUP BY 1) c ON c.parent_id = pa.id
                         WHERE upper(pa.ticker) = upper(?) OR pa.name ILIKE ? ORDER BY (upper(pa.ticker) = upper(?)) DESC,
                         c.n DESC NULLS LAST LIMIT 1""", [q, f"%{q}%", q])
    return row


def company(arg: str) -> list[Reply]:
    if not arg.strip():
        return [Reply("Which company? e.g. `/company cipla`")]
    g = _find_group(arg)
    if not g:
        return [Reply(f"No corporate group matches '{arg}'.")]
    cur = db.cursor()
    pid = g["id"]
    q = db.one(cur, "SELECT price, change_pct, market_cap, quoted_at FROM quotes WHERE ticker = ?", [f"{g['ticker']}.NS"]) if g["ticker"] else None
    skus = cur.execute("""SELECT count(*), count(*) FILTER (WHERE NOT coalesce(is_discontinued, false))
                          FROM products p JOIN companies c ON c.id = p.company_id WHERE c.parent_id = ?""", [pid]).fetchone()
    since = (datetime.now() - timedelta(days=365)).strftime("%Y-%m")
    nsq = cur.execute("""SELECT count(*), count(*) FILTER (WHERE n.alert_month >= ?), max(n.alert_month)
                         FROM reg_nsq n JOIN companies c ON c.id = n.company_id WHERE c.parent_id = ?""", [since, pid]).fetchone()
    fda = cur.execute("SELECT count(*), max(issued_on) FROM usfda_actions WHERE parent_id = ?", [pid]).fetchone()
    sec = cur.execute("""SELECT count(*), count(*) FILTER (WHERE outcome = 'recommended') FROM sec_items
                         WHERE parent_id = ? AND meeting_date >= current_date - INTERVAL 365 DAY""", [pid]).fetchone()
    news = cur.execute("""SELECT title, source FROM news WHERE list_contains(string_split(parent_ids, ','), ?)
                          ORDER BY published_at DESC LIMIT 3""", [str(pid)]).fetchall()
    lines = [f"**{g['name']}**" + (f" · NSE {g['ticker']}" if g["ticker"] else " · unlisted")]
    if q and q.get("price"):
        lines.append(f"Share ₹{q['price']:,.1f} ({(q.get('change_pct') or 0):+.2f}%)"
                     + (f" · m-cap ₹{q['market_cap'] / 1e7:,.0f} Cr" if q.get("market_cap") else ""))
    lines.append(f"Portfolio: {skus[1]:,} active SKUs ({skus[0]:,} listed)")
    lines.append(f"Quality: {nsq[1]} failed-batch listings in 12 months, {nsq[0]} all time" + (f" (latest {nsq[2]})" if nsq[2] else ""))
    lines.append(f"US FDA actions: {fda[0]}" + (f" (latest {fda[1]})" if fda[1] else ""))
    lines.append(f"CDSCO expert committee, 12 months: {sec[0]} items, {sec[1]} recommended")
    if news:
        lines.append("Latest news:")
        lines += [f"- {t[:110]} ({s})" for t, s in news]
    row1 = [cb("Quality chart", f"chart:q:{pid}")] + ([cb("Share chart", f"chart:t:{g['ticker']}")] if g["ticker"] else [])
    return [Reply("\n".join(lines), [row1, [cb("More news", f"news:{pid}"), link("Open in terminal", f"/g/{g['slug']}")]])]


def news_for(pid: str) -> list[Reply]:
    rows = db.cursor().execute("""SELECT title, source, url, published_at FROM news WHERE list_contains(string_split(parent_ids, ','), ?)
                                  ORDER BY published_at DESC LIMIT 10""", [pid]).fetchall()
    if not rows:
        return [Reply("No tagged news for this group.")]
    return [Reply("\n".join(f"- [{t[:100]}]({u}) · {s}, {p:%d %b}" for t, s, u, p in rows))]


# ------------------------------------------------------------------ /chart
def chart(arg: str) -> list[Reply]:
    a = arg.strip()
    if not a or a.lower() in ("nsq", "quality", "market"):
        return chart_cb("qm")
    if a.lower() in ("nifty", "nifty pharma", "pharma"):
        return chart_cb("t:^CNXPHARMA")
    g = _find_group(a)
    if g and g["ticker"]:
        return chart_cb(f"t:{g['ticker']}")
    if g:
        return chart_cb(f"q:{g['id']}")
    from ..api.routers.catalog import search
    hits = (search(q=a, limit=1) or {}).get("products") or []
    if hits:
        return chart_cb(f"p:{hits[0]['id']}")
    return [Reply(f"Nothing to chart for '{a}'. Try a company, a ticker, a brand, or `nsq`.")]


def chart_cb(arg: str) -> list[Reply]:
    kind, _, val = arg.partition(":")
    if kind == "t":
        name = db.cursor().execute("SELECT name FROM parents WHERE ticker = ?", [val]).fetchone()
        png = charts.stock(val, name[0] if name else ("NIFTY Pharma" if val == "^CNXPHARMA" else val))
    elif kind == "q":
        g = db.cursor().execute("SELECT name FROM parents WHERE id = ?", [int(val)]).fetchone()
        ids = [r[0] for r in db.cursor().execute("SELECT id FROM companies WHERE parent_id = ?", [int(val)]).fetchall()]
        png = charts.nsq_monthly(g[0] if g else "Group", ids or [-1])
    elif kind == "qm":
        png = charts.nsq_monthly("India")
    elif kind == "p":
        png = charts.product_prices(int(val))
    else:
        png = None
    return [Reply(photo=png)] if png else [Reply("Not enough data to draw that yet.")]


# ------------------------------------------------------------------ /feeds and /status
def feeds(_: str = "") -> list[Reply]:
    from ..connectors import REGISTRY
    from ..connectors.health import expected_gap
    cur = db.cursor()
    last = {r[0]: r[1:] for r in cur.execute("""SELECT connector, status, finished_at, message FROM (
        SELECT *, row_number() OVER (PARTITION BY connector ORDER BY started_at DESC) rn FROM connector_runs) WHERE rn = 1""").fetchall()}
    last_ok = dict(cur.execute("SELECT connector, max(finished_at) FROM connector_runs WHERE status = 'ok' GROUP BY 1").fetchall())
    bad, stale = [], []
    for name, cls in REGISTRY.items():
        st = last.get(name)
        if st and st[0] == "error":
            bad.append((name, cls.title, (st[2] or "")[:90]))
        elif last_ok.get(name) and datetime.now() - last_ok[name] > expected_gap(cls.schedule):
            stale.append((name, cls.title))
    lines = [f"**Feeds**: {len(REGISTRY) - len(bad) - len(stale)} of {len(REGISTRY)} healthy"]
    lines += [f"🔴 {t}: {m}" for _, t, m in bad]
    lines += [f"🟠 {t}: no success for longer than its schedule" for _, t in stale]
    if not bad and not stale:
        lines.append("All green. Suspicious, but green.")
    buttons = [[cb(f"Run {t[:28]}", f"run:{n}")] for n, t, _ in bad[:5]]
    return [Reply("\n".join(lines), buttons + [[link("Feed board", "/feeds")]])]


def run_ask(name: str) -> list[Reply]:
    from ..connectors import REGISTRY
    if name not in REGISTRY:
        return [Reply(f"No feed called {name}.")]
    return [Reply(f"Run **{REGISTRY[name].title}** now?", [[cb("Yes, run it", f"runyes:{name}"), cb("No", "noop")]])]


def run_yes(name: str) -> list[Reply]:
    from .. import scheduler
    res = {}
    t = threading.Thread(target=lambda: res.update(scheduler.run_now(name)), daemon=True)
    t.start()
    t.join(timeout=240)
    if not res:
        return [Reply(f"{name} is still running; I'll stay out of its way. Check /feeds in a few minutes.")]
    return [Reply(f"**{name}**: {res.get('status')} in {res.get('seconds')}s · {res.get('rows_new', 0):,} new rows"
                  + (f"\n{(res.get('message') or '')[:300]}" if res.get("message") else ""))]


def status(_: str = "") -> list[Reply]:
    lines = ["**Server**"]
    try:
        la = os.getloadavg()
        lines.append(f"Load {la[0]:.2f} / {la[1]:.2f} / {la[2]:.2f}")
    except (OSError, AttributeError):
        pass
    try:
        mem = dict(l.split(":", 1) for l in open("/proc/meminfo").read().splitlines() if ":" in l)
        tot, avail = (int(mem[k].split()[0]) / 1024 for k in ("MemTotal", "MemAvailable"))
        lines.append(f"Memory {tot - avail:,.0f} / {tot:,.0f} MB used")
    except OSError:
        pass
    du = shutil.disk_usage(DATA_DIR)
    lines.append(f"Disk {du.free / 2**30:.1f} GB free of {du.total / 2**30:.0f} GB · database {os.path.getsize(DB_PATH) / 2**30:.2f} GB")
    up = timedelta(seconds=int(time.time() - STARTED))
    lines.append(f"App up {up}")
    cur = db.cursor()
    tls = cur.execute("SELECT value FROM connector_state WHERE starts_with(key, 'tlsrev|')").fetchall()
    if tls:
        import json
        st = [json.loads(v[0])["status"] for v in tls]
        lines.append(f"TLS: {st.count('good')} good, {st.count('revoked')} revoked, {st.count('unknown')} unknown, {st.count('error')} error")
    mark = os.getenv("PHARMALENS_BACKUP_MARK", "/srv/backups/last_run.txt")
    if os.path.exists(mark):
        lines.append(f"Last backup {datetime.fromtimestamp(os.path.getmtime(mark)):%d %b %H:%M}")
    return [Reply("\n".join(lines))]


# ------------------------------------------------------------------ /brief
def brief(arg: str = "") -> list[Reply]:
    hours = int(arg) if arg.strip().isdigit() else 12
    text, _ = briefing.write(briefing.label_for(), briefing.default_since(hours))
    return [Reply(text, brief_buttons(hours))]


def brief_buttons(hours: int) -> list[list[tuple[str, str]]]:
    return [[cb("All events", f"events:{hours}"), cb("Quality chart", "chart:qm")],
            [cb("Feeds", "feeds"), link("Terminal", "/")]]


def events(hours: str) -> list[Reply]:
    h = int(hours) if str(hours).isdigit() else 12
    rows = db.cursor().execute("""SELECT severity, kind, title, url FROM events WHERE detected_at > now() - to_hours(?)
                                  AND kind NOT IN ('news', 'stock')
                                  ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                                  detected_at DESC LIMIT 20""", [h]).fetchall()
    if not rows:
        return [Reply(f"No events in the last {h} hours.")]
    icon = {"critical": "🔴", "high": "🔴", "medium": "🟠"}
    lines = [f"**Events, last {h} h** (most serious first)"]
    lines += [f"{icon.get(s, '⚪')} " + (f"[{t[:120]}]({u})" if u else t[:120]) for s, k, t, u in rows]
    return [Reply("\n".join(lines))]


# ------------------------------------------------------------------ /export
def export(question: str) -> list[Reply]:
    if not question.strip():
        return [Reply("Ask for a table, e.g. `/export top 50 companies by NSQ batches in 2026`")]
    from . import llm, tools
    spec = [t for t in tools.TOOL_SPECS if t["name"] in ("sql_query", "describe_tables")]
    system = ("Write ONE DuckDB SELECT that answers the request, test it with sql_query (fix errors and retry), then reply "
              "with a one-line description of the table. Data notes: " + EXPORT_NOTES)
    turns, last_sql = [{"role": "user", "text": question}], None
    for _ in range(6):
        step = llm.complete(system, turns, spec)
        turns.append(step)
        if not step["calls"]:
            break
        for c in step["calls"]:
            res = tools.call(c["name"], c["args"])
            if c["name"] == "sql_query" and isinstance(res, dict) and "rows" in res:
                last_sql = c["args"].get("sql")
            turns.append({"role": "tool", "id": c["id"], "name": c["name"], "result": res})
    if not last_sql:
        return [Reply("Couldn't build a working query for that. Rephrase, or ask me in plain words first.")]
    cur = db.cursor()
    res = cur.execute(f"SELECT * FROM ({last_sql.strip().rstrip(';')}) LIMIT 20000")
    cols = [d[0] for d in res.description]
    rows = res.fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    w.writerows(rows)
    name = re.sub(r"[^a-z0-9]+", "_", question.lower())[:40].strip("_") or "export"
    # the model's one-line description, without any SQL it echoed (the query is shown separately below)
    note = next((l.strip() for l in (turns[-1].get("text") or "").splitlines()
                 if l.strip() and not re.search(r"\bselect\b|\bfrom\b|```", l, re.I)), "")[:300]
    return [Reply(document=(f"{name}.csv", buf.getvalue().encode("utf-8-sig")),
                  text=f"{len(rows):,} rows · {len(cols)} columns. {note}\n<code>{last_sql[:600]}</code>")]


EXPORT_NOTES = ("companies.parent_id -> parents.id; reg_nsq(alert_month 'YYYY-MM', category NSQ|SPURIOUS, company_id); "
                "products(company_id, mrp, mrp_asof, pack_size, unit_price, combo_id, is_discontinued); "
                "molecule_ids columns are comma lists: list_contains(string_split(molecule_ids, ','), '<id>').")


# ------------------------------------------------------------------ routing
HANDLERS = {"help": help_, "start": help_, "brief": brief, "check": check, "company": company, "chart": chart,
            "export": export, "feeds": feeds, "status": status}
CALLBACKS = {"brief": lambda a: brief(a), "check": lambda a: product_card(int(a)), "cheap": cheap, "chart": chart_cb,
             "news": news_for, "feeds": feeds, "run": run_ask, "runyes": run_yes, "events": events,
             "noop": lambda a: [Reply("Fine. Nothing touched.")]}


def command(name: str, arg: str) -> list[Reply] | None:
    fn = HANDLERS.get(name)
    return fn(arg) if fn else None


def callback(data: str) -> list[Reply]:
    action, _, arg = data.partition(":")
    fn = CALLBACKS.get(action)
    return fn(arg) if fn else [Reply("That button has expired.")]
