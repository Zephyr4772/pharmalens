"""Tools the DrugDen agent can call. Reads run immediately; actions return a confirmation request instead of acting."""
import json
import threading
from datetime import datetime
from pathlib import Path

import duckdb

from .. import db, scheduler
from ..config import REPO_ROOT

DOCS = {"sources": "docs/SOURCES.md", "methodology": "docs/METHODOLOGY.md", "handoff": "HANDOFF.md", "readme": "README.md"}
SQL_ROW_LIMIT = 60
SQL_TIMEOUT_S = 20


def _json(v):
    return json.loads(json.dumps(v, default=str))


def sql_query(sql: str) -> dict:
    """Run one read-only SELECT against the live database (DuckDB classifies the statement before it runs)."""
    cur = db.cursor()
    try:
        stmts = cur.extract_statements(sql)
    except duckdb.Error as e:
        return {"error": f"SQL does not parse: {str(e)[:300]}"}
    if len(stmts) != 1 or stmts[0].type != duckdb.StatementType.SELECT:
        return {"error": "only a single SELECT (or WITH ... SELECT) statement is allowed"}
    timer = threading.Timer(SQL_TIMEOUT_S, cur.interrupt)
    timer.start()
    try:
        res = cur.execute(f"SELECT * FROM ({sql.strip().rstrip(';')}) LIMIT {SQL_ROW_LIMIT + 1}")
        cols = [d[0] for d in res.description]
        rows = res.fetchall()
    except duckdb.Error as e:
        return {"error": str(e)[:400]}
    finally:
        timer.cancel()
    return _json({"columns": cols, "rows": [list(r) for r in rows[:SQL_ROW_LIMIT]],
                  "truncated": len(rows) > SQL_ROW_LIMIT})


def describe_tables(pattern: str = "") -> dict:
    cur = db.cursor()
    rows = cur.execute("""SELECT table_name, string_agg(column_name || ' ' || data_type, ', ' ORDER BY ordinal_position)
                          FROM information_schema.columns WHERE table_schema = 'main' AND table_name ILIKE ?
                          GROUP BY 1 ORDER BY 1""", [f"%{pattern}%"]).fetchall()
    counts = {}
    for (t, _) in rows[:80]:
        try:
            counts[t] = cur.execute(f'SELECT count(*) FROM "{t}"').fetchall()[0][0]
        except duckdb.Error:
            counts[t] = None
    return _json({"tables": [{"table": t, "rows": counts.get(t), "columns": c} for t, c in rows[:80]]})


def feed_status(name: str = "") -> dict:
    from ..connectors import REGISTRY
    cur = db.cursor()
    last = {r[0]: r[1:] for r in cur.execute("""
        SELECT connector, status, finished_at, rows_seen, rows_new, message FROM (
          SELECT *, row_number() OVER (PARTITION BY connector ORDER BY started_at DESC) rn FROM connector_runs) WHERE rn = 1""").fetchall()}
    last_ok = dict(cur.execute("SELECT connector, max(finished_at) FROM connector_runs WHERE status = 'ok' GROUP BY 1").fetchall())
    nxt = scheduler.jobs()
    out = []
    for n, cls in REGISTRY.items():
        if name and name.lower() not in (n + " " + cls.title).lower():
            continue
        l = last.get(n)
        out.append({"feed": n, "title": cls.title, "source": cls.agency, "what": cls.description,
                    "last_status": l[0] if l else None, "last_run": l[1] if l else None, "last_success": last_ok.get(n),
                    "rows_seen": l[2] if l else None, "rows_new": l[3] if l else None, "note": (l[4] or "")[:200] if l else None,
                    "next_run": nxt.get(n), "schedule": cls.schedule})
    return _json({"now": datetime.now(), "feeds": out})


def read_doc(name: str, query: str = "") -> dict:
    path = DOCS.get(name)
    if not path or not (REPO_ROOT / path).exists():
        return {"error": f"unknown doc; available: {list(DOCS)}"}
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    if query:
        # sections mentioning the query, to keep the context small
        secs = [s for s in text.split("\n## ") if query.lower() in s.lower()]
        text = "\n## ".join(secs) or text
    return {"doc": name, "text": text[:12000]}


def search_catalog(q: str) -> dict:
    from ..api.routers.catalog import search
    return _json(search(q=q, limit=8))


def news(query: str = "", days: int = 14, topic: str = "") -> dict:
    """Latest stories from our news wire (Indian pharma press + GDELT archive), newest first."""
    cur = db.cursor()
    where, args = ["published_at >= now() - to_days(?)"], [max(1, min(int(days or 14), 3650))]
    if query:
        where.append("(title ILIKE ? OR coalesce(summary, '') ILIKE ?)")
        args += [f"%{query}%"] * 2
    if topic:
        where.append("topic = ?")
        args.append(topic.lower())
    rows = cur.execute(f"""SELECT published_at, source, topic, title, url FROM news WHERE {' AND '.join(where)}
                           ORDER BY published_at DESC LIMIT 15""", args).fetchall()
    total = cur.execute(f"SELECT count(*) FROM news WHERE {' AND '.join(where)}", args).fetchall()[0][0]
    return _json({"matching": total, "stories": [dict(zip(["published", "source", "topic", "title", "url"], r)) for r in rows]})


def recent_events(kind: str = "", severity: str = "", hours: int = 48, query: str = "") -> dict:
    """The alert tape: what the feeds detected recently (bans, NSQ, spurious, recalls, approvals, filings, stock moves...)."""
    cur = db.cursor()
    where, args = ["coalesce(detected_at, ts) >= now() - to_hours(?)"], [max(1, min(int(hours or 48), 24 * 365))]
    if kind:
        where.append("kind = ?")
        args.append(kind.lower())
    if severity:
        where.append("severity IN (SELECT unnest(string_split(?, ',')))")
        args.append(severity.lower().replace(" ", ""))
    if query:
        where.append("(title ILIKE ? OR coalesce(body, '') ILIKE ?)")
        args += [f"%{query}%"] * 2
    w = " AND ".join(where)
    rows = cur.execute(f"""SELECT ts, kind, severity, title, source, url FROM events WHERE {w}
                           ORDER BY coalesce(detected_at, ts) DESC LIMIT 25""", args).fetchall()
    by_kind = cur.execute(f"SELECT kind, count(*) FROM events WHERE {w} GROUP BY 1 ORDER BY 2 DESC", args).fetchall()
    return _json({"counts_by_kind": dict(by_kind),
                  "events": [dict(zip(["when", "kind", "severity", "title", "source", "url"], r)) for r in rows]})


def web_news(query: str, days: int = 7) -> dict:
    """Live news search on any topic (Google News RSS, India edition, last N days)."""
    import xml.etree.ElementTree as ET
    from urllib.parse import quote
    import httpx
    days = max(1, min(int(days or 7), 365))
    url = f"https://news.google.com/rss/search?q={quote(query)}+when:{days}d&hl=en-IN&gl=IN&ceid=IN:en"
    r = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 DrugDen/1.0"})
    if r.status_code != 200:
        return {"error": f"news search {r.status_code}"}
    items = ET.fromstring(r.content).findall("./channel/item")[:15]
    return _json({"articles": [{"date": i.findtext("pubDate"), "source": i.findtext("source"), "title": i.findtext("title"),
                                "url": i.findtext("link")} for i in items]})


def _public_host(host: str) -> bool:
    import ipaddress
    import socket
    try:
        addrs = {i[4][0] for i in socket.getaddrinfo(host, None)}
    except OSError:
        return False
    return all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addrs)


def fetch_page(url: str) -> dict:
    """Read the text of a public web page (e.g. a link the owner sends, or a source document)."""
    import re
    from urllib.parse import urlparse
    import httpx
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname or not _public_host(u.hostname):
        return {"error": "only public http(s) pages can be read"}
    r = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 DrugDen/1.0"})
    if r.url.host and not _public_host(r.url.host):
        return {"error": "redirected to a non-public address"}
    ctype = r.headers.get("content-type", "")
    if "pdf" in ctype:
        return {"status": r.status_code, "note": "this is a PDF; its text is not extracted here", "bytes": len(r.content)}
    text = r.text
    if "html" in ctype:
        text = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;|&#160;", " ", text)
        text = re.sub(r"\s+", " ", text)
    return {"status": r.status_code, "url": str(r.url), "text": text.strip()[:9000]}


def resolve_names(text: str) -> dict:
    """Which companies, groups, molecules or indices a name (or a whole sentence) refers to, with database ids."""
    from . import names
    found = names.find(text)
    if not found:
        found = names.resolve(text, limit=5)
    return _json({"matches": [{k: v for k, v in e.items() if k in ("type", "id", "name", "ticker", "group_id", "score", "matched")}
                              for e in found]})


# ---- actions (confirmation required)
def run_feed(name: str) -> dict:
    from ..connectors import REGISTRY
    if name not in REGISTRY:
        return {"error": f"unknown feed {name}"}
    return {"needs_confirmation": True, "action": "run_feed", "args": {"name": name},
            "summary": f"Run the '{REGISTRY[name].title}' feed now"}


def do_action(action: str, args: dict) -> dict:
    if action == "run_feed":
        res = {}
        t = threading.Thread(target=lambda: res.update(scheduler.run_now(args["name"])), daemon=True)
        t.start()
        t.join(timeout=240)
        return _json(res or {"status": "started; still running in the background"})
    return {"error": f"unknown action {action}"}


TOOLS = [
    {"name": "sql_query", "fn": sql_query,
     "description": "Run ONE read-only SQL SELECT on the live DuckDB database (DuckDB dialect) and get up to 60 rows. "
                    "Use describe_tables first if unsure of table or column names. Aggregate in SQL rather than fetching many rows.",
     "parameters": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}},
    {"name": "describe_tables", "fn": describe_tables,
     "description": "List database tables with row counts and columns. Optional substring filter on table name.",
     "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}}},
    {"name": "feed_status", "fn": feed_status,
     "description": "Status of the data feeds (connectors): last run, last success, rows fetched, next scheduled run, source. "
                    "Use for any question about freshness, schedules or whether something is working. Optional name filter.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}}}},
    {"name": "read_doc", "fn": read_doc,
     "description": "Read project documentation: 'sources' (every data source and its status), 'methodology' (how data is "
                    "matched and computed), 'handoff' (project state, server, decisions), 'readme'. Optional query keeps matching sections.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string", "enum": list(DOCS)}, "query": {"type": "string"}},
                    "required": ["name"]}},
    {"name": "search_catalog", "fn": search_catalog,
     "description": "Search products (brands), molecules, combinations, companies and groups by name.",
     "parameters": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}},
    {"name": "news", "fn": news,
     "description": "Our pharma news wire (Indian trade/business press, refreshed every 15 min, archive back to 2017). "
                    "Optional text query (company, drug, topic words), days back (default 14), topic (regulatory, pricing, "
                    "approval, recall, deal, earnings, litigation, supply, policy, quality, general).",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "days": {"type": "integer"},
                                                     "topic": {"type": "string"}}}},
    {"name": "recent_events", "fn": recent_events,
     "description": "What the feeds detected recently: the alert tape. kind: nsq, spurious, ban, price_notification, "
                    "approval, recall, launch, usfda, news, stock, shortage, gazette, tender, filing. severity: comma list of "
                    "critical, high, medium, info. hours back (default 48). Optional text query. Use for 'what happened today'.",
     "parameters": {"type": "object", "properties": {"kind": {"type": "string"}, "severity": {"type": "string"},
                                                     "hours": {"type": "integer"}, "query": {"type": "string"}}}},
    {"name": "web_news", "fn": web_news,
     "description": "Live news search on any topic (Google News, last N days, default 7). Use when our own wire has "
                    "nothing, for non-Indian or non-pharma news, or for the very latest.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "days": {"type": "integer"}},
                    "required": ["query"]}},
    {"name": "fetch_page", "fn": fetch_page,
     "description": "Read the text of a public web page by URL (a link the owner sent, a news story or a source page).",
     "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "resolve_names", "fn": resolve_names,
     "description": "Resolve company / group / molecule / index names as the owner typed them (short forms, tickers, "
                    "nicknames, typos: 'sun', 'drl', 'glenmrk', 'cadila') to canonical names and database ids. Use it "
                    "before querying whenever a name is not already resolved in the message context.",
     "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "run_feed", "fn": run_feed,
     "description": "Request running a data feed immediately (asks the owner to confirm first). Use the feed name from feed_status.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
]
TOOL_FNS = {t["name"]: t["fn"] for t in TOOLS}
TOOL_SPECS = [{k: v for k, v in t.items() if k != "fn"} for t in TOOLS]


def call(name: str, args: dict) -> dict:
    fn = TOOL_FNS.get(name)
    if not fn:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(**(args or {}))
    except TypeError as e:
        return {"error": f"bad arguments: {e}"}
    except Exception as e:  # noqa: BLE001 — tool errors go back to the model, not up the stack
        return {"error": f"{type(e).__name__}: {str(e)[:300]}"}
