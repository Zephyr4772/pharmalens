"""Briefings: what happened since the last one, ranked by importance and written up by the model.

Facts come from the database only (events, news, quotes, feed runs); the model only words and orders them. When no
model answers, a plain template is sent instead, so a briefing never fails.
"""
import json
import logging
from collections import Counter
from datetime import datetime, timedelta

from .. import db
from . import llm

log = logging.getLogger("drugden.briefing")
SEV_W = {"critical": 6, "high": 4, "medium": 2, "info": 1}
KIND_W = {"spurious": 3, "ban": 3, "results": 3, "recall": 2, "usfda": 2, "shortage": 2, "price_notification": 2, "trial": 2,
          "nsq": 1, "launch": 1, "approval": 1, "filing": 1, "results_due": 1, "gazette": 1, "tender": 0}
NEWS_TOPICS = ("regulatory", "pricing", "quality", "recall", "deal", "approval", "policy", "supply", "litigation")

STYLE = """You write DrugDen's {label} for its owner on Telegram: a sharp equity / industry analyst's brief on the
Indian pharma market and the data pipeline, read on a phone between meetings. Think like an investor: results and
margins, regulatory risk (US FDA, CDSCO quality failures, bans), governance red flags (regulatory orders, litigation,
senior exits), pipeline (approvals, trials stopped or advanced), pricing actions. Use ONLY the facts in the JSON.
Never invent numbers, names or causes.

Format (plain text, phone-sized):
**{label}**: one-line headline summing up the period.
Then 3-6 bullets "- ", most important first. Each: what happened, then " → " and why it matters in a few words
(who is affected, what to watch). Group related items (many NSQ batches = one bullet naming the top makers).
Then one line starting "Market:" if market data is given, and one line "Pipeline:" with feed health in a few words.
No preamble, no sign-off, no tables, no # headings. Max ~900 characters."""


def gather(since: datetime) -> dict:
    cur = db.cursor()
    now = datetime.now()
    ev = cur.execute("""SELECT kind, severity, title, url, coalesce(source, '') FROM events
                        WHERE detected_at > ? AND kind NOT IN ('news', 'stock') ORDER BY detected_at DESC LIMIT 400""",
                     [since]).fetchall()
    ranked = sorted(ev, key=lambda e: -(SEV_W.get(e[1], 1) + KIND_W.get(e[0], 0)))
    nsq = [e for e in ev if e[0] in ("nsq", "spurious")]
    others = [e for e in ranked if e[0] not in ("nsq", "spurious")][:10]
    makers = Counter(dict(cur.execute("""SELECT c.name, count(*) FROM reg_nsq n JOIN companies c ON c.id = n.company_id
                                         WHERE n.fetched_at > ? GROUP BY 1""", [since]).fetchall()))
    news = cur.execute(f"""SELECT title, source, topic FROM news WHERE fetched_at > ? AND published_at > ? - INTERVAL 2 DAY
                           AND topic IN ({','.join('?' * len(NEWS_TOPICS))}) ORDER BY published_at DESC LIMIT 8""",
                       [since, now, *NEWS_TOPICS]).fetchall()
    movers = cur.execute("""SELECT p.name, q.change_pct FROM quotes q JOIN parents p ON q.ticker = p.ticker || '.NS'
                            WHERE q.change_pct IS NOT NULL AND q.quoted_at > ? ORDER BY abs(q.change_pct) DESC LIMIT 4""",
                         [since]).fetchall()
    index = cur.execute("SELECT price, change_pct FROM quotes WHERE ticker = '^CNXPHARMA' AND quoted_at > ?", [since]).fetchone()
    runs = cur.execute("""SELECT count(DISTINCT connector), count(*) FILTER (WHERE status = 'error'), sum(rows_new)
                          FROM connector_runs WHERE finished_at > ?""", [since]).fetchone()
    failing = [r[0] for r in cur.execute("""SELECT connector FROM (SELECT connector, status, row_number() OVER
                                            (PARTITION BY connector ORDER BY started_at DESC) rn FROM connector_runs)
                                            WHERE rn = 1 AND status = 'error'""").fetchall()]
    return {
        "period": f"{since:%d %b %H:%M} to {now:%d %b %H:%M} IST",
        "top_events": [{"kind": k, "severity": s, "title": t[:220]} for k, s, t, _, _ in others],
        "quality_failures": {"batches": len(nsq), "spurious": sum(1 for e in nsq if e[0] == "spurious"),
                             "top_makers": makers.most_common(4)} if nsq else None,
        "news": [{"title": t[:180], "source": s, "topic": tp} for t, s, tp in news],
        "market": {"nifty_pharma": {"level": index[0], "change_pct": index[1]} if index else None,
                   "movers": [{"group": n, "change_pct": round(c, 2)} for n, c in movers]} if (index or movers) else None,
        "pipeline": {"feeds_ran": runs[0], "run_errors": runs[1], "new_rows": int(runs[2] or 0), "currently_failing": failing},
    }


def notable(facts: dict) -> bool:
    return bool(facts["top_events"] or facts["quality_failures"] or facts["news"])


def template(label: str, f: dict) -> str:
    """Plain fallback when no model is reachable."""
    lines = [f"**{label}** ({f['period']})"]
    for e in f["top_events"][:5]:
        lines.append(f"- {e['title']}")
    if f["quality_failures"]:
        q = f["quality_failures"]
        lines.append(f"- {q['batches']} failed batches ({q['spurious']} spurious); most from "
                     + ", ".join(f"{m} ({n})" for m, n in q["top_makers"]))
    for n in f["news"][:3]:
        lines.append(f"- {n['title']} ({n['source']})")
    if f["market"] and f["market"]["movers"]:
        lines.append("Market: " + ", ".join(f"{m['group']} {m['change_pct']:+.1f}%" for m in f["market"]["movers"]))
    p = f["pipeline"]
    lines.append(f"Pipeline: {p['feeds_ran']} feeds ran, {p['new_rows']:,} new rows"
                 + (f", failing: {', '.join(p['currently_failing'])}" if p["currently_failing"] else ", all healthy"))
    return "\n".join(lines)


def write(label: str, since: datetime) -> tuple[str, dict]:
    """(text, facts). Quiet periods get one honest line instead of a padded report."""
    f = gather(since)
    if not notable(f):
        p = f["pipeline"]
        return (f"**{label}**: quiet. Nothing notable since {since:%d %b %H:%M}. {p['feeds_ran']} feeds ran"
                + (f", failing: {', '.join(p['currently_failing'])}." if p["currently_failing"] else ", all healthy."), f)
    try:
        step = llm.complete(STYLE.format(label=label),
                            [{"role": "user", "text": json.dumps(f, default=str, ensure_ascii=False)}], [])
        text = (step.get("text") or "").strip()
        if len(text) > 60:
            return text, f
    except Exception as e:  # noqa: BLE001 — a briefing must still go out on the template
        log.warning("briefing model failed: %s", e)
    return template(label, f), f


def label_for(now: datetime | None = None) -> str:
    h = (now or datetime.now()).hour
    return "Morning brief" if h < 12 else "Midday brief" if h < 17 else "Evening wrap"


def default_since(hours: int = 12) -> datetime:
    return datetime.now() - timedelta(hours=hours)
