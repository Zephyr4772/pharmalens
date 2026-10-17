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
_company: dict[str, int] | None = None      # firm key -> id (largest wins)
_company_nospace: dict[str, int] = {}
_parents: list[tuple[int, list[re.Pattern], str]] | None = None
_parent_alias: dict[str, int] | None = None  # short names used in news ('sun pharma', 'dr reddy')

# words that collide with molecule names in prose
MOLECULE_STOP = {"iron", "zinc", "water", "oxygen", "sugar", "salt", "honey", "calcium", "sodium", "potassium",
                 "magnesium", "vitamin", "alcohol", "charcoal", "glycerin", "lactose", "starch", "gold", "silver",
                 "powder", "tablet", "tablets", "capsule", "device", "light", "solution", "injection", "syrup"}


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
        global _company_nospace
        comp: dict[str, int] = {}
        # with descriptors kept, catalog rows sharing a key are one firm spelled two ways ("J B Chemicals & / and
        # Pharmaceuticals"); the entry with the most products represents it
        for cid, name, name_norm in cur.execute(
                "SELECT id, name, name_norm FROM companies ORDER BY product_count DESC NULLS LAST, id").fetchall():
            for k in {firm_key(name), firm_key(name_norm or "")} - {""}:
                comp.setdefault(k, cid)
        _company = comp
        # PDF text often splits words ("ALKEM LABORATORIE S", "Biopharmaceutica ls"): also index keys without spaces
        _company_nospace = {}
        for cid, name, name_norm in cur.execute(
                "SELECT id, name, name_norm FROM companies ORDER BY product_count DESC NULLS LAST, id").fetchall():
            for k in {firm_squash(name), firm_squash(name_norm or "")} - {""}:
                _company_nospace.setdefault(k, cid)
        seed = json.loads((SEED_DIR / "parents.json").read_text(encoding="utf-8"))
        ids = dict(cur.execute("SELECT slug, id FROM parents").fetchall())
        from .normalize import slugify
        _parents = []
        alias = {}
        for p in seed:
            pid = ids.get(slugify(p["name"]))
            if pid is None:
                continue
            _parents.append((pid, [re.compile(x) for x in p["patterns"]], p["name"],
                             [re.compile(x) for x in p.get("india_patterns", [])], [re.compile(x) for x in p.get("global_patterns", [])]))
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


# words that only say what kind of legal entity it is; everything else (Biotech, Remedies, Healthcare, Surgical...)
# distinguishes companies (Hindustan Laboratories != Hindustan Biotech, Bharat Serum != Bharat Biotech)
FIRM_LEGAL = {"pvt", "private", "ltd", "limited", "llp", "inc", "co", "corp", "corporation", "company", "the", "m", "s", "ms",
              "india", "i", "p", "and"}
FIRM_SYNONYM = {"formulation": "formulations", "pharmaceuticals": "pharma", "pharmaceutical": "pharma", "pharmaceuitical": "pharma", "pharmaceuiticals": "pharma",
                "pharms": "pharma", "laboratories": "labs", "laboratory": "labs", "lab": "labs", "lifescience": "lifesciences",
                "phamra": "pharma", "limted": "limited", "privet": "private"}


def _firm_text(name: str) -> str:
    """Firm name only: list numbers and M/s dropped, cut at the legal suffix (whatever follows is an address or
    plant: '... Ltd Indore', '... Limited (Plant-2)'), then at commas / unit / plot / village markers."""
    s = re.sub(r"^\s*(?:\d+\.\s*)?(?:m\s*/\s*s\b\.?\s*)?", "", name or "", flags=re.I)
    m = re.search(r"\b(?:pvt\.?\s*ltd|private\s+limited|limited|ltd|llp|inc)\b\.?", s, flags=re.I)
    if m:
        s = s[:m.end()]
    s = re.split(r",|\(formerly|\(a div|\bunit\b|\bplot\b|\bvill|\s-\s|\s-(?=[a-z])", s, maxsplit=1, flags=re.I)[0]
    return norm(s)


SQUASH_DROP = {"pvt", "private", "ltd", "limited", "llp", "inc", "india", "the", "co", "corp", "company", "corporation", "ms", "and"}


def firm_squash(name: str) -> str:
    """Letters only, legal words removed, no synonyms: repairs words split by PDF extraction
    ('ALKEM LABORATORIE S LTD' -> 'alkemlaboratories')."""
    return "".join(t for t in _firm_text(name).split() if t not in SQUASH_DROP)


def firm_key(name: str) -> str:
    """'M/s. Unicure (India) Pvt. Ltd., Roorkee' and 'UNICURE (INDIA) LTD' -> 'unicure';
    'Zee Laboratories Limited' and 'Zee Labs Ltd' -> 'zee labs'. Distinguishing descriptors are kept."""
    t = _firm_text(name).replace("life sciences", "lifesciences").replace("life science", "lifesciences").replace("health care", "healthcare")
    toks = [FIRM_SYNONYM.get(x, x) for x in t.split()]
    toks = [FIRM_SYNONYM.get(x, x) for x in toks if x not in FIRM_LEGAL]
    return " ".join(x for x in toks if x not in FIRM_LEGAL)


def company_for(name: str | None) -> int | None:
    """Catalog company for a manufacturer string, only when the whole firm name matches one company.
    No prefix guessing: an unknown firm stays unlinked rather than being attributed to a namesake."""
    if not name:
        return None
    _load()
    name = re.sub(r"\bm\s*/\s*s\b\.?", " ", name, flags=re.I)   # "M/s." prefixes, before splitting on "/"
    candidates = name.split("/")          # "Unicure India Pvt Ltd/Unicure India Ltd"
    # earlier name of a renamed firm: "Cipco Limited (Formerly Known As Cipco Pharmaceuticals)"
    candidates += re.findall(r"formerly\s+(?:known\s+as\s+)?([^)]+)\)", name, flags=re.I)
    for part in candidates:
        k = firm_key(part)
        if k and k in _company:
            return _company[k]
        q = firm_squash(part)
        if len(q) >= 8 and q in _company_nospace:
            return _company_nospace[q]
    # a unit/division named after its owner: "Unique Pharmaceutical Laboratories (a div of J. B. Chemicals ...)",
    # "Alkem Health Science A Unit of Alkem Laboratories Ltd" -> the owning firm
    m = re.search(r"\ba\s+(?:div(?:ision)?|unit)\.?\s+of\s+(?:m\s*/\s*s\.?\s*)?([^)]+)", name, flags=re.I)
    if m:
        k = firm_key(m.group(1))
        return _company.get(k) if k else None
    return None


def parent_for(name: str | None, region: str = "india") -> int | None:
    """Parent group for a firm name. region="global" for foreign registries (FDA, WHO, EMA, trials), where a bare
    "Merck" or "Cadila" means a different company than it does on an Indian label."""
    if not name:
        return None
    _load()
    k = norm_company(name)
    full = norm(name)
    for pid, rxs, _, india, glob in _parents:
        if any(r.search(k) or r.search(full) for r in rxs):
            return pid
        # region-specific patterns are exact short forms ("merck", "cadila"): test the full name, not the
        # suffix-stripped one, so "Cadila Pharmaceuticals Ltd" never reads as the bare "Cadila"
        if region == "india" and any(r.search(k) or r.search(full) for r in india):
            return pid
        if region != "india" and any(r.search(full) for r in glob):
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


# formulation ingredients that appear in full compositions (CDSCO approvals list the whole formula)
EXCIPIENTS = {"water for injection", "water", "sucrose", "trehalose", "polysorbate", "polysorbate 80", "polysorbate 20", "histidine",
              "l histidine", "sodium chloride", "glycine", "arginine", "methionine", "sodium citrate", "citric acid", "acetic acid",
              "sodium acetate", "sodium hydroxide", "hydrochloric acid", "phosphate", "sodium phosphate", "disodium hydrogen phosphate",
              "mannitol", "sorbitol", "glycerin", "glycerol", "lactose", "starch", "magnesium stearate", "talc", "povidone",
              "microcrystalline cellulose", "croscarmellose", "hypromellose", "titanium dioxide", "edetate disodium", "benzyl alcohol",
              "metacresol", "phenol", "zinc oxide", "tromethamine", "dextrose", "maltose", "poloxamer", "polyethylene glycol", "macrogol"}


def actives_in(name: str, composition: str = "", limit: int = 8) -> list[int]:
    """Active molecules of an approved product, read from its name; formulation excipients never count."""
    # the name only: when it names no catalog molecule (a new biologic), the composition offers only excipients
    # and salts (romosozumab's formula -> "calcium"), so no link is better than a wrong one
    _load()
    skip = {_mol.get(molecule_key(x)) for x in EXCIPIENTS} - {None}
    return [m for m in molecules_in(name or "", limit=limit) if m not in skip]
