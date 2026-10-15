"""Entity resolution from free text (regulator PDFs, news, inventory uploads).

Indexes are loaded lazily from the catalog and cached in-process; call reset()
after a core rebuild.
"""
import json
import re
import threading

from . import db
from .config import SEED_DIR
from .normalize import molecule_key, norm, norm_company

_lock = threading.Lock()
_mol: dict[str, int] | None = None          # molecule key -> id
_mol_maxlen = 1
_company: dict[str, int] | None = None      # heavy-normalized company -> id (largest wins)
_parents: list[tuple[int, list[re.Pattern], str]] | None = None
_parent_alias: dict[str, int] | None = None  # short names used in news ('sun pharma', 'dr reddy')

# words that collide with molecule names in prose
MOLECULE_STOP = {"iron", "zinc", "water", "oxygen", "sugar", "salt", "honey", "calcium", "sodium", "potassium",
                 "magnesium", "vitamin", "alcohol", "charcoal", "glycerin", "lactose", "starch", "gold", "silver"}


def reset():
    global _mol, _company, _parents, _parent_alias
    with _lock:
        _mol = _company = _parents = _parent_alias = None


def _load():
    global _mol, _mol_maxlen, _company, _parents, _parent_alias
    with _lock:
        if _mol is not None:
            return
        cur = db.cursor()
        mol = {}
        for mid, mkey, pc in cur.execute("SELECT id, mkey, coalesce(product_count,0) FROM molecules").fetchall():
            if pc >= 1 and len(mkey) >= 4:
                mol[mkey] = mid
        _mol = mol
        _mol_maxlen = max((len(k.split()) for k in mol), default=1)
        comp = {}
        for cid, name, pc in cur.execute(
            "SELECT id, name, coalesce(product_count,0) FROM companies ORDER BY product_count DESC NULLS LAST"
        ).fetchall():
            k = norm_company(name)
            if k and k not in comp:
                comp[k] = cid
        _company = comp
        seed = json.loads((SEED_DIR / "parents.json").read_text(encoding="utf-8"))
        ids = dict(cur.execute("SELECT slug, id FROM parents").fetchall())
        from .normalize import slugify
        _parents = []
        alias = {}
        for p in seed:
            pid = ids.get(slugify(p["name"]))
            if pid is None:
                continue
            _parents.append((pid, [re.compile(x) for x in p["patterns"]], p["name"]))
            short = norm(p["name"]).replace(" laboratories", "").replace(" pharmaceuticals", "").replace(" pharmaceutical industries", "")
            # tickers/short names that are ordinary words in pharma prose are not aliases
            for a in {short, norm(p["name"])}:
                if a and len(a) >= 4 and a not in {"fdc", "star", "eris", "gland", "micro", "bayer s", "usv"}:
                    alias[a] = pid
        # common shorthand in news
        for a, nm in [("sun pharma", "Sun Pharmaceutical Industries"), ("dr reddy", "Dr. Reddy's Laboratories"),
                      ("dr reddys", "Dr. Reddy's Laboratories"), ("zydus", "Zydus Lifesciences"),
                      ("glenmark", "Glenmark Pharmaceuticals"), ("aurobindo", "Aurobindo Pharma"),
                      ("torrent pharma", "Torrent Pharmaceuticals"), ("alkem", "Alkem Laboratories"),
                      ("mankind", "Mankind Pharma"), ("gsk pharma", "GlaxoSmithKline Pharmaceuticals"),
                      ("biocon", "Biocon"), ("lupin", "Lupin"), ("cipla", "Cipla"), ("intas", "Intas Pharmaceuticals"),
                      ("divi s", "Divi's Laboratories"), ("divis", "Divi's Laboratories"), ("natco", "Natco Pharma"),
                      ("ipca", "Ipca Laboratories"), ("wockhardt", "Wockhardt"), ("granules", "Granules India"),
                      ("laurus", "Laurus Labs"), ("emcure", "Emcure Pharmaceuticals"), ("abbott india", "Abbott India")]:
            pid = ids.get(slugify(nm))
            if pid:
                alias[a] = pid
        _parent_alias = alias


def molecules_in(text: str, limit: int = 12) -> list[int]:
    """Molecule ids mentioned in text (longest n-gram first, no overlaps)."""
    _load()
    toks = norm(text).split()
    found, i = [], 0
    while i < len(toks) and len(found) < limit:
        hit = None
        for n in range(min(_mol_maxlen, 5, len(toks) - i), 0, -1):
            cand = " ".join(toks[i:i + n])
            if n == 1 and (cand in MOLECULE_STOP or len(cand) < 5):
                continue
            k = molecule_key(cand)
            mid = _mol.get(cand) or (_mol.get(k) if k else None)
            if mid:
                hit = (mid, n)
                break
        if hit:
            if hit[0] not in found:
                found.append(hit[0])
            i += hit[1]
        else:
            i += 1
    return found


def company_for(name: str | None) -> int | None:
    """Best catalog company for a manufacturer string like 'M/s. Zee Laboratories Ltd., Paonta Sahib'."""
    if not name:
        return None
    _load()
    s = re.sub(r"^\s*m\s*/\s*s\.?\s*", "", name, flags=re.I)
    s = re.split(r",|\(|\bplot\b|\bvill", s, maxsplit=1, flags=re.I)[0]
    k = norm_company(s)
    if not k:
        return None
    if k in _company:
        return _company[k]
    toks = k.split()
    for n in range(len(toks) - 1, 0, -1):
        kk = " ".join(toks[:n])
        if kk in _company and len(kk) >= 4:
            return _company[kk]
    return None


def parent_for(name: str | None) -> int | None:
    if not name:
        return None
    _load()
    k = norm_company(name)
    full = norm(name)
    for pid, rxs, _ in _parents:
        if any(r.search(k) or r.search(full) for r in rxs):
            return pid
    return None


def parents_in(text: str, limit: int = 6) -> list[int]:
    """Parent groups mentioned in prose (news headlines)."""
    _load()
    t = f" {norm(text)} "
    out = []
    for alias, pid in sorted(_parent_alias.items(), key=lambda x: -len(x[0])):
        if f" {alias} " in t and pid not in out:
            out.append(pid)
            if len(out) >= limit:
                break
    return out
