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


GDELT_QUERIES = [
    ("CDSCO / DCGI", '(CDSCO OR DCGI OR "drug controller") sourcecountry:india'),
    ("NPPA pricing", '(NPPA OR "ceiling price" OR DPCO OR "drug price") sourcecountry:india'),
    ("USFDA India", '(USFDA OR "warning letter" OR "import alert" OR "form 483") pharma sourcecountry:india'),
    ("Quality / bans", '("not of standard quality" OR "spurious drugs" OR "banned drugs" OR "fixed dose combination") sourcecountry:india'),
    ("Pharma deals", 'pharma (acquisition OR acquires OR merger OR stake) sourcecountry:india'),
    ("Jan Aushadhi / policy", '("Jan Aushadhi" OR "Department of Pharmaceuticals" OR "PLI scheme" pharma) sourcecountry:india'),
]


class NewsArchive(Connector):
    name = "news_archive"
    title = "Pharma News Archive (GDELT)"
    agency = "GDELT Project"
    schedule = {"trigger": "cron", "hour": "*/2", "minute": 25}
    description = "Back-catalogue of Indian pharma news since 2017 from the GDELT index, month by month, tagged like the live wire."
    START = (2017, 1)
    per_run = 120          # GDELT allows one request every 5 s

    def months(self):
        y, m = self.START
        today = datetime.utcnow()
        while (y, m) <= (today.year, today.month):
            yield y, m
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    def run(self):
        import json
        import time
        from urllib.parse import quote
        cur = db.cursor()
        done = {r[0] for r in cur.execute("SELECT key FROM connector_state WHERE key LIKE 'gdelt|%'").fetchall()}
        now = datetime.utcnow()
        todo = []
        for y, m in self.months():
            current = (y, m) == (now.year, now.month) or (y, m) == ((now - timedelta(days=28)).year, (now - timedelta(days=28)).month)
            for label, q in GDELT_QUERIES:
                k = f"gdelt|{y:04d}-{m:02d}|{label}"
                if k not in done or current:          # the last two months are re-read so late items land
                    todo.append((y, m, label, q, k))
        todo.sort(key=lambda t: (t[0], t[1]), reverse=True)  # newest first
        seen_titles = {norm(r[0]) for r in cur.execute("SELECT title FROM news").fetchall()}
        calls = 0
        for y, m, label, q, k in todo:
            if calls >= self.per_run:
                break
            start = f"{y:04d}{m:02d}01000000"
            ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
            end = f"{ny:04d}{nm:02d}01000000"
            url = (f"https://api.gdeltproject.org/api/v2/doc/doc?query={quote(q)}&mode=artlist&format=json&maxrecords=250"
                   f"&sort=datedesc&startdatetime={start}&enddatetime={end}")
            data = None
            for attempt in range(3):
                time.sleep(6)
                calls += 1
                r = self.get(url, timeout=90)
                body = r.text.strip()
                if body.startswith("Please limit"):
                    time.sleep(20)
                    continue
                try:
                    data = json.loads(body) if body else {"articles": []}
                except ValueError:
                    data = None
                break
            if data is None:
                continue
            arts = data.get("articles") or []
            with db.writer() as w:
                for a in arts:
                    title = re.sub(r"\s+", " ", a.get("title") or "").strip()
                    link = a.get("url")
                    nt = norm(title)
                    if not title or not link or nt in seen_titles or (a.get("language") or "English") != "English":
                        continue
                    if w.execute("SELECT 1 FROM news WHERE url = ?", [link]).fetchone():
                        continue
                    try:
                        ts = datetime.strptime(a.get("seendate", "")[:15], "%Y%m%dT%H%M%S")
                    except ValueError:
                        continue
                    pids = matcher.parents_in(title)
                    mids = matcher.molecules_in(title, limit=5)
                    w.execute("""INSERT INTO news (published_at, source, title, url, summary, topic, parent_ids, molecule_ids, fetched_at)
                                 VALUES (?,?,?,?,NULL,?,?,?, now())""",
                              [ts, a.get("domain") or "GDELT", title, link, classify(title),
                               ",".join(map(str, pids)) or None, ",".join(map(str, mids)) or None])
                    seen_titles.add(nt)
                    self.stats.rows_new += 1
                self.stats.rows_seen += len(arts)
                w.execute("INSERT OR REPLACE INTO connector_state VALUES (?, ?)", [k, datetime.now().isoformat()])
        left = max(0, len(todo) - calls)
        self.stats.notes.append(f"{calls} GDELT queries · {self.stats.rows_new:,} new articles" + (f" · ~{left} month-topics left" if left else ""))
