"""Name understanding: every company, corporate group, ticker and molecule under all the ways people write them.

`build()` writes data/name_index.json (rebuilt daily by the name_index feed and on first use): each entry has a type
(group | company | molecule), id, canonical name and aliases: the full name, the name without legal / industry
suffixes, the NSE ticker, a distinctive first word when no other entity uses it, initials, and hand-curated nicknames.
`resolve(text)` answers "which entity is this?" (exact alias, then fuzzy for typos); `find(sentence)` spots every
entity mentioned in free text, so the bot knows what "sun vs drl margins" is about before it thinks.
"""
import json
import re
import threading
from datetime import datetime

from rapidfuzz import fuzz, process

from .. import db
from ..config import DATA_DIR
from ..normalize import norm

INDEX = DATA_DIR / "name_index.json"
SUFFIX = {"ltd", "limited", "pvt", "private", "inc", "llp", "co", "corp", "corporation", "company", "the", "m", "s", "ms",
          "india", "indian", "pharma", "pharmaceutical", "pharmaceuticals", "laboratories", "laboratory", "labs", "lab",
          "industries", "industry", "healthcare", "health", "care", "lifesciences", "life", "sciences", "science",
          "remedies", "biotech", "drugs", "chemicals", "formulations", "global", "international", "and"}
# nicknames people actually use; values are group names as stored in `parents`
NICKNAMES = {
    "drl": "Dr. Reddy's Laboratories", "dr reddy": "Dr. Reddy's Laboratories", "reddys": "Dr. Reddy's Laboratories",
    "reddy": "Dr. Reddy's Laboratories", "sun": "Sun Pharmaceutical Industries", "sun pharma": "Sun Pharmaceutical Industries",
    "ranbaxy": "Sun Pharmaceutical Industries", "cadila": "Zydus Lifesciences", "zydus cadila": "Zydus Lifesciences",
    "zydus": "Zydus Lifesciences", "divis": "Divi's Laboratories", "divi": "Divi's Laboratories", "auro": "Aurobindo Pharma",
    "aurobindo": "Aurobindo Pharma", "jb chem": "JB Chemicals & Pharmaceuticals", "jbcp": "JB Chemicals & Pharmaceuticals",
    "jb": "JB Chemicals & Pharmaceuticals", "gsk": "GlaxoSmithKline Pharmaceuticals", "glaxo": "GlaxoSmithKline Pharmaceuticals",
    "p&g": "Procter & Gamble Health", "pg health": "Procter & Gamble Health", "torrent": "Torrent Pharmaceuticals",
    "abbott": "Abbott India", "mankind": "Mankind Pharma", "glenmark": "Glenmark Pharmaceuticals", "ipca": "Ipca Laboratories",
    "alkem": "Alkem Laboratories", "biocon": "Biocon", "lupin": "Lupin", "cipla": "Cipla", "natco": "Natco Pharma",
    "laurus": "Laurus Labs", "gland": "Gland Pharma", "granules": "Granules India", "ajanta": "Ajanta Pharma",
    "eris": "Eris Lifesciences", "emcure": "Emcure Pharmaceuticals", "piramal": "Piramal Pharma", "wockhardt": "Wockhardt",
    "strides": "Strides Pharma", "intas": "Intas Pharmaceuticals", "macleods": "Macleods Pharmaceuticals",
}
INDICES = [("^CNXPHARMA", "NIFTY Pharma", ["nifty pharma", "pharma index", "cnxpharma", "nifty pharma index"]),
           ("^NSEI", "NIFTY 50", ["nifty", "nifty 50", "nifty50", "market"])]
_lock = threading.Lock()
_cache: dict | None = None


def _key(s: str) -> str:
    return re.sub(r"\s+", " ", norm(s.replace("'", "").replace("&", " and "))).strip()


def _core(name: str) -> str:
    words = [w for w in _key(name).split() if w not in SUFFIX]
    return " ".join(words)


def _initials(name: str) -> str | None:
    words = [w for w in _key(name).split() if w not in {"the", "and", "of", "ltd", "limited", "pvt", "private"}]
    return "".join(w[0] for w in words) if len(words) >= 3 else None


def build() -> dict:
    """Assemble the index from the database and write it as JSON. Returns {'entries': [...], 'built': iso}."""
    cur = db.cursor()
    groups = cur.execute("""SELECT pa.id, pa.name, pa.ticker, coalesce(sum(c.product_count), 0) FROM parents pa
                            LEFT JOIN companies c ON c.parent_id = pa.id GROUP BY 1, 2, 3""").fetchall()
    companies = cur.execute("""SELECT id, name, parent_id, coalesce(product_count, 0) FROM companies
                               WHERE coalesce(product_count, 0) > 0 AND name NOT ILIKE 'lorem%'""").fetchall()
    molecules = cur.execute("SELECT id, name, coalesce(product_count, 0) FROM molecules WHERE coalesce(product_count, 0) > 0").fetchall()
    # a first word is a safe alias only if no other group/company starts with it ("sun" yes, "indian" no)
    first = {}
    for _, name, *_ in [(g[0], g[1]) for g in groups] + [(c[0], c[1]) for c in companies]:
        core = _core(name).split()
        if core:
            first[core[0]] = first.get(core[0], 0) + 1
    entries = []
    for gid, name, ticker, size in groups:
        al = {_key(name), _core(name)}
        if ticker:
            al |= {ticker.lower(), _key(ticker)}
        core = _core(name).split()
        if core and len(core[0]) >= 4 and first.get(core[0]) == 1:
            al.add(core[0])
        if (ini := _initials(name)):
            al.add(ini)
        al |= {k for k, v in NICKNAMES.items() if v == name}
        entries.append({"type": "group", "id": gid, "name": name, "ticker": ticker, "size": int(size), "aliases": sorted(a for a in al if a)})
    for cid, name, parent_id, size in companies:
        al = {_key(name), _core(name)}
        core = _core(name).split()
        if core and len(core[0]) >= 5 and first.get(core[0]) == 1:
            al.add(core[0])
        entries.append({"type": "company", "id": cid, "name": name, "group_id": parent_id, "size": int(size),
                        "aliases": sorted(a for a in al if a and len(a) >= 3)})
    for mid, name, size in molecules:
        entries.append({"type": "molecule", "id": mid, "name": name, "size": int(size), "aliases": sorted({_key(name), _core(name)} - {""})})
    for ticker, name, al in INDICES:
        entries.append({"type": "index", "id": ticker, "name": name, "ticker": ticker, "size": 10**9, "aliases": al})
    out = {"built": datetime.now().isoformat(timespec="seconds"), "entries": entries}
    INDEX.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    _load(force=True)
    return out


def _load(force: bool = False) -> dict:
    """alias -> [entry], cached in memory; built on first use if the JSON is missing."""
    global _cache
    with _lock:
        if _cache is not None and not force:
            return _cache
        if not INDEX.exists():
            data = None
        else:
            data = json.loads(INDEX.read_text(encoding="utf-8"))
    if data is None:
        return build_and_cache()
    alias: dict[str, list] = {}
    for e in data["entries"]:
        for a in e["aliases"]:
            alias.setdefault(a, []).append(e)
    rank = {"index": 0, "group": 0, "company": 1, "molecule": 2}
    for a in alias:   # groups first, then the biggest
        alias[a].sort(key=lambda e: (rank[e["type"]], -e.get("size", 0)))
    with _lock:
        _cache = {"alias": alias, "keys": list(alias), "built": data["built"], "n": len(data["entries"])}
    return _cache


def build_and_cache() -> dict:
    build()
    return _cache


def resolve(text: str, types: tuple[str, ...] = ("index", "group", "company", "molecule"), limit: int = 5) -> list[dict]:
    """Best entities for a name as typed. Exact alias first; otherwise fuzzy (typos, word order) above a safe score."""
    idx = _load()
    k = _key(text)
    if not k:
        return []
    hits = [e for e in idx["alias"].get(k, []) if e["type"] in types]
    if not hits and _core(text):
        hits = [e for e in idx["alias"].get(_core(text), []) if e["type"] in types]
    if hits:
        return [_out(e, 100, k) for e in hits[:limit]]
    out, seen = [], set()
    for alias, score, _ in process.extract(k, idx["keys"], scorer=fuzz.WRatio, limit=25):
        if score < 86 or abs(len(alias) - len(k)) > max(6, len(k)):
            continue
        for e in idx["alias"][alias]:
            if e["type"] in types and (e["type"], e["id"]) not in seen:
                seen.add((e["type"], e["id"]))
                out.append(_out(e, round(score), alias))
    out.sort(key=lambda x: (-x["score"], {"index": 0, "group": 0, "company": 1, "molecule": 2}[x["type"]], -x.get("size", 0)))
    return out[:limit]


def _out(e: dict, score: int, matched: str) -> dict:
    return {k: v for k, v in e.items() if k != "aliases"} | {"score": score, "matched": matched}


def find(sentence: str, types: tuple[str, ...] = ("index", "group", "company", "molecule")) -> list[dict]:
    """Entities mentioned anywhere in free text (longest phrase first, exact aliases only, no overlaps)."""
    idx = _load()
    toks = _key(sentence).split()
    found, i = [], 0
    while i < len(toks):
        hit = None
        for n in range(min(5, len(toks) - i), 0, -1):
            phrase = " ".join(toks[i:i + n])
            if n == 1 and (len(phrase) < 3 or phrase in SUFFIX or phrase in STOP):
                continue
            ents = [e for e in idx["alias"].get(phrase, []) if e["type"] in types]
            if ents:
                hit = (_out(ents[0], 100, phrase), n)
                break
        if hit:
            if all((h["type"], h["id"]) != (hit[0]["type"], hit[0]["id"]) for h in found):
                found.append(hit[0])
            i += hit[1]
        else:
            i += 1
    return found


STOP = {"the", "and", "for", "with", "what", "how", "why", "who", "show", "tell", "about", "news", "price", "prices", "share",
        "stock", "today", "this", "that", "week", "month", "year", "vs", "versus", "compare", "best", "top", "any", "all",
        "check", "chart", "results", "profit", "sales", "revenue", "quality", "batch", "batches", "drug", "drugs", "medicine",
        "company", "companies", "group", "market", "india", "indian", "new", "latest", "risk", "margin", "margins", "data"}


def describe(found: list[dict]) -> str:
    """One line per entity, for the agent's context."""
    parts = []
    for e in found:
        if e["type"] == "group":
            parts.append(f"'{e['matched']}' = group {e['name']} (parents.id {e['id']}" + (f", NSE {e['ticker']}" if e.get("ticker") else ", unlisted") + ")")
        elif e["type"] == "company":
            parts.append(f"'{e['matched']}' = company {e['name']} (companies.id {e['id']}" + (f", group parents.id {e['group_id']}" if e.get("group_id") else "") + ")")
        elif e["type"] == "index":
            parts.append(f"'{e['matched']}' = index {e['name']} (quotes / quote_history ticker {e['ticker']})")
        else:
            parts.append(f"'{e['matched']}' = molecule {e['name']} (molecules.id {e['id']})")
    return "; ".join(parts)
