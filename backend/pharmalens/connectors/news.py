"""Pharma news aggregation with entity tagging and topic classification."""
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser

from .. import db, matcher
from ..normalize import norm
from .base import BROWSER_UA, Connector

FEEDS = [
    ("ET HealthWorld Pharma", "https://health.economictimes.indiatimes.com/rss/pharma"),
    ("Express Pharma", "https://www.expresspharma.in/feed/"),
    ("Google News: India pharma", "https://news.google.com/rss/search?q=pharma+india+when:3d&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Google News: CDSCO / DCGI", "https://news.google.com/rss/search?q=(CDSCO+OR+DCGI+OR+%22drug+controller%22)+when:7d&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Google News: NPPA pricing", "https://news.google.com/rss/search?q=(NPPA+OR+%22ceiling+price%22+OR+DPCO)+when:7d&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Google News: USFDA India plants", "https://news.google.com/rss/search?q=USFDA+(warning+letter+OR+%22form+483%22+OR+%22import+alert%22+OR+inspection)+India+when:7d&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Google News: banned FDC / NSQ", "https://news.google.com/rss/search?q=(%22banned%22+OR+%22NSQ%22+OR+%22spurious%22)+drugs+India+when:7d&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Google News: pharma deals", "https://news.google.com/rss/search?q=pharma+(acquisition+OR+acquires+OR+merger+OR+stake)+India+when:7d&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Google News: pharma results", "https://news.google.com/rss/search?q=pharma+(%22Q1%22+OR+%22Q2%22+OR+%22Q3%22+OR+%22Q4%22+OR+results+OR+profit)+India+when:7d&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Google News: drug shortage India", "https://news.google.com/rss/search?q=(%22drug+shortage%22+OR+%22medicine+shortage%22+OR+stockout)+India+when:14d&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Google News: Jan Aushadhi / PLI", "https://news.google.com/rss/search?q=(%22Jan+Aushadhi%22+OR+%22PLI+scheme%22+pharma+OR+%22Department+of+Pharmaceuticals%22)+when:14d&hl=en-IN&gl=IN&ceid=IN:en"),
]

TOPICS = [
    ("recall", r"\brecall"),
    ("quality", r"\bnsq\b|not of standard quality|spurious|substandard|falsified|counterfeit|adulterat"),
    ("regulatory", r"usfda|\bfda\b|warning letter|form 483|import alert|observation|cdsco|dcgi|inspection|schedule m|gazette|\bban\b|banned|prohibit"),
    ("pricing", r"nppa|ceiling price|dpco|price cap|price hike|price revision|trade margin|overcharg"),
    ("approval", r"approv|launch|nod\b|clearance|go-ahead|introduc"),
    ("deal", r"acqui|merger|stake|buyout|takeover|joint venture|\bjv\b|divest|licens|partnership|tie-up|ties up"),
    ("earnings", r"\bq[1-4]\b|quarter|profit|revenue|earnings|results|ebitda|guidance|net loss"),
    ("supply", r"shortage|stockout|supply chain|api import|\bkspm\b|china|raw material"),
    ("litigation", r"patent|lawsuit|litigation|court|settlement|infring"),
    ("policy", r"policy|pli\b|scheme|budget|ministry|jan aushadhi|ayushman|tariff|gst"),
]
TOPIC_RX = [(t, re.compile(p, re.I)) for t, p in TOPICS]
TOPIC_SEVERITY = {"recall": "high", "quality": "high", "regulatory": "medium", "pricing": "medium"}


def classify(text: str) -> str:
    for t, rx in TOPIC_RX:
        if rx.search(text):
            return t
    return "general"


def entry_time(e) -> datetime | None:
    for k in ("published", "updated"):
        v = e.get(k)
        if v:
            try:
                dt = parsedate_to_datetime(v)
                return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
            except (TypeError, ValueError):
                pass
    return None


def clean_title(t: str) -> tuple[str, str | None]:
    """Google News titles end with ' - Publisher'."""
    m = re.match(r"^(.*)\s+-\s+([^-]{2,60})$", t.strip())
    return (m.group(1).strip(), m.group(2).strip()) if m else (t.strip(), None)


class PharmaNews(Connector):
    name = "pharma_news"
    title = "Pharma News Wire"
    agency = "RSS"
    schedule = {"trigger": "interval", "minutes": 15}
    description = "ET HealthWorld, Express Pharma and targeted Google News queries; deduped, tagged to companies and molecules."

    def run(self):
        cutoff = datetime.utcnow() - timedelta(days=21)
        seen_titles = {norm(r[0]) for r in db.cursor().execute(
            "SELECT title FROM news WHERE published_at > now() - INTERVAL 10 DAY").fetchall()}
        for src, url in FEEDS:
            f = feedparser.parse(url, agent=BROWSER_UA)
            if not f.entries:
                self.stats.notes.append(f"{src}: 0 entries")
                continue
            with db.writer() as cur:
                for e in f.entries:
                    link = e.get("link")
                    if not link:
                        continue
                    title, publisher = clean_title(e.get("title", ""))
                    nt = norm(title)
                    if not nt or nt in seen_titles:
                        continue
                    ts = entry_time(e) or datetime.utcnow()
                    if ts < cutoff:
                        continue
                    self.stats.rows_seen += 1
                    if cur.execute("SELECT 1 FROM news WHERE url = ?", [link]).fetchone():
                        continue
                    summary = re.sub(r"<[^>]+>", " ", e.get("summary", "") or "")
                    summary = re.sub(r"\s+", " ", summary).strip()[:600]
                    if summary.lower().startswith(title.lower()[:40].lower()):
                        summary = ""
                    topic = classify(f"{title} {summary}")
                    pids = matcher.parents_in(title)
                    mids = matcher.molecules_in(title, limit=5)
                    cur.execute(
                        """INSERT INTO news (published_at, source, title, url, summary, topic, parent_ids, molecule_ids, fetched_at)
                           VALUES (?,?,?,?,?,?,?,?, now())""",
                        [ts, publisher or src, title, link, summary or None, topic,
                         ",".join(map(str, pids)) or None, ",".join(map(str, mids)) or None],
                    )
                    seen_titles.add(nt)
                    self.stats.rows_new += 1
                    if topic in TOPIC_SEVERITY or pids:
                        self.emit(cur, kind="news", severity=TOPIC_SEVERITY.get(topic, "info"), ts=ts,
                                  title=title, url=link, entity_type="parent" if pids else None,
                                  entity_id=pids[0] if pids else None, dedupe_key=f"news|{link}",
                                  payload={"topic": topic, "publisher": publisher or src})
