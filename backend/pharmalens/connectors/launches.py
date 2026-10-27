"""New-brand detection: remember when each brand first appears in a registry and announce the arrivals.

Two registries feed it: the CDSCO Rule 84AB brand-name registry (weekly snapshot) and CDCI, the national drug
terminology (monthly, with its own per-brand update date). The first time a source is tracked, everything already
there is the baseline; for the CDSCO registry the archived weekly snapshots are replayed oldest first, so brands that
appeared between two archived snapshots count as new on the later snapshot's date.
"""
import json
import re
from collections import Counter
from datetime import date, datetime

import pandas as pd

from .. import matcher
from ..config import RAW_DIR
from ..normalize import norm
from .base import Connector

RECENT_DAYS = 21   # arrivals newer than this are announced


def _known(w, source: str) -> set[str]:
    return {r[0] for r in w.execute("SELECT key FROM brand_first_seen WHERE source = ?", [source]).fetchall()}


def track(w, source: str, items: list[dict], seen_on: date | None, baseline: bool) -> list[dict]:
    """Insert the items not seen before; returns them. Each item: key, brand, firm, generic, license, company_id."""
    known = _known(w, source)
    new = list({it["key"]: it for it in items if it["key"] not in known}.values())
    if new:
        # one bulk insert: row-by-row inserts into a keyed table exhaust DuckDB's memory at baseline size (~90k)
        df = pd.DataFrame([{"source": source, "key": it["key"], "brand": it["brand"], "brand_norm": norm(it["brand"]),
                            "firm": it.get("firm"), "generic": it.get("generic"), "license": it.get("license"),
                            "company_id": it.get("company_id"), "first_seen": it.get("seen_on") or seen_on,
                            "baseline": baseline} for it in new])
        df["company_id"] = df["company_id"].astype("Int64")
        w.register("_bfs", df)
        w.execute("""INSERT INTO brand_first_seen SELECT source, key, brand, brand_norm, firm, generic, license,
                     company_id::INTEGER, first_seen::DATE, baseline FROM _bfs""")
        w.unregister("_bfs")
    return new


def registry_items(rows: list[dict]) -> list[dict]:
    """CDSCO 84AB rows (firm_name, license_number, brand_name, generic_name) -> tracker items."""
    out = []
    for r in rows:
        firm = (r.get("firm_name") or "").strip()
        lic = (r.get("license_number") or "").strip()
        brand = (r.get("brand_name") or "").strip()
        generic = (r.get("generic_name") or "").strip()
        out.append({"key": f"{norm(firm)}|{lic}|{norm(brand)}", "brand": brand, "firm": firm,
                    "generic": None if generic in ("", "-") else generic, "license": lic or None})
    return out


def seed_registry_from_archives(w) -> int:
    """Replay archived weekly snapshots oldest first: the first is the baseline, later ones date the arrivals."""
    files = sorted(RAW_DIR.glob("cdsco_brands/*/brands-*.json"))
    for i, f in enumerate(files):
        m = re.search(r"brands-(\d{8})", f.name)
        seen_on = datetime.strptime(m.group(1), "%Y%m%d").date() if m else date.today()
        items = registry_items(json.loads(f.read_text(encoding="utf-8")))
        for it in items:
            it["company_id"] = None   # resolved for the arrivals only (below), the baseline does not need it
        new = track(w, "cdsco_84ab", items, seen_on, baseline=(i == 0))
        if i:
            for it in new:
                w.execute("UPDATE brand_first_seen SET company_id = ? WHERE source = 'cdsco_84ab' AND key = ?",
                          [matcher.company_for(it["firm"]), it["key"]])
    return len(files)


def announce(conn: Connector, w, source_label: str, new: list[dict], seen_on: date):
    """One summary event per run, plus one per arrival from a company that belongs to a tracked group."""
    if not new:
        return
    by_firm = Counter(it.get("firm") or "unknown firm" for it in new)
    top = ", ".join(f"{f} {n}" for f, n in by_firm.most_common(4)) + (f" +{len(by_firm) - 4} more" if len(by_firm) > 4 else "")
    sample = "; ".join(f"{it['brand']} ({(it.get('generic') or '?')[:60]})" for it in new[:6])
    conn.emit(w, kind="launch", severity="info", ts=seen_on,
              title=f"{source_label}: {len(new)} new brand name{'s' * (len(new) > 1)} registered ({top})",
              body=sample, dedupe_key=f"newbrands|{source_label}|{seen_on}|{len(new)}")
    grouped = 0
    for it in new:
        cid = it.get("company_id")
        if not cid or grouped >= 15:
            continue
        parent = w.execute("SELECT p.name FROM companies c JOIN parents p ON p.id = c.parent_id WHERE c.id = ?", [cid]).fetchone()
        if parent:
            grouped += 1
            generic = f" ({it['generic'][:80]})" if it.get("generic") else ""
            conn.emit(w, kind="launch", severity="info", ts=seen_on, entity_type="company", entity_id=cid,
                      title=f"New brand registered by {parent[0]}: {it['brand']}{generic}",
                      dedupe_key=f"newbrand|{source_label}|{it['key']}")
