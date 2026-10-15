"""Name/composition normalization shared by the core build and all connectors."""
import re
import unicodedata

WS = re.compile(r"\s+")
NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
COMPANY_STOP = {
    "pvt", "private", "ltd", "limited", "llp", "co", "corp", "corporation", "inc",
    "the", "m", "s", "ms", "and", "pharmaceuticals", "pharmaceutical", "pharma",
    "laboratories", "laboratory", "labs", "lab", "industries", "india", "healthcare",
    "lifesciences", "life", "sciences", "remedies", "formulations", "biotech",
}
# spelling variants that matter for molecule matching (Indian vs INN spelling)
MOLECULE_ALIASES = {
    "amoxycillin": "amoxicillin",
    "paracetamol": "paracetamol",
    "acetaminophen": "paracetamol",
    "cephalexin": "cefalexin",
    "cefalexin": "cefalexin",
    "salbutamol": "salbutamol",
    "albuterol": "salbutamol",
    "frusemide": "furosemide",
    "glibenclamide": "glibenclamide",
    "glyburide": "glibenclamide",
    "levothyroxine sodium": "levothyroxine",
    "thyroxine": "levothyroxine",
    "clavulanic acid": "clavulanic acid",
    "potassium clavulanate": "clavulanic acid",
    "diclofenac sodium": "diclofenac",
    "diclofenac potassium": "diclofenac",
    "pantoprazole sodium": "pantoprazole",
    "rabeprazole sodium": "rabeprazole",
    "esomeprazole magnesium": "esomeprazole",
    "metformin hydrochloride": "metformin",
    "metformin hcl": "metformin",
    "chlorpheniramine maleate": "chlorpheniramine",
    "chlorphenamine": "chlorpheniramine",
    "phenylephrine hydrochloride": "phenylephrine",
    "cetirizine hydrochloride": "cetirizine",
    "ondansetron hydrochloride": "ondansetron",
    "atorvastatin calcium": "atorvastatin",
    "rosuvastatin calcium": "rosuvastatin",
    "amlodipine besylate": "amlodipine",
    "amlodipine besilate": "amlodipine",
    "losartan potassium": "losartan",
    "telmisartan": "telmisartan",
    "dextromethorphan hydrobromide": "dextromethorphan",
    "ambroxol hydrochloride": "ambroxol",
    "bromhexine hydrochloride": "bromhexine",
    "ofloxacin": "ofloxacin",
    "ciprofloxacin hydrochloride": "ciprofloxacin",
    "vitamin c": "ascorbic acid",
    "vitamin b12": "methylcobalamin",
    "caffeine anhydrous": "caffeine",
}
SALT_SUFFIXES = (
    " hydrochloride", " hcl", " sodium", " potassium", " calcium", " magnesium",
    " maleate", " besylate", " besilate", " mesylate", " succinate", " tartrate",
    " citrate", " sulphate", " sulfate", " phosphate", " acetate", " fumarate",
    " hydrobromide", " dihydrate", " monohydrate", " trihydrate", " anhydrous",
    " ip", " bp", " usp",
)


def ascii_fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = ascii_fold(str(s)).lower()
    s = NON_ALNUM.sub(" ", s)
    return WS.sub(" ", s).strip()


def norm_product(name: str | None) -> str:
    return norm(name)


def norm_company(name: str | None) -> str:
    toks = [t for t in norm(name).split() if t not in COMPANY_STOP]
    return " ".join(toks)


def slugify(s: str, max_len: int = 64) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", ascii_fold(s).lower()).strip("-")
    return out[:max_len].rstrip("-") or "x"


GLUED_COMPANY = re.compile(
    r"^.*?\b(?:pvt ltd|private limited|ltd|limited|llp|laboratories|labs|pharmaceuticals|pharma|healthcare|"
    r"lifesciences|life sciences|biotech|remedies|biosciences)(?=[a-z])"
)
TRAILING_NUM = re.compile(r"(?:\s+\d+(?:\s+\d+)*)+$")


def molecule_key(name: str | None) -> str:
    """Strength-free, salt-form-free key: 'Amoxycillin Trihydrate' -> 'amoxicillin'.
    Returns '' for strings that are clearly not a molecule."""
    k = norm(name)
    if not k:
        return ""
    # scrape artefact: manufacturer glued onto the first molecule ('scotmed care pvt ltdazithromycin')
    k = GLUED_COMPANY.sub("", k).strip()
    k = TRAILING_NUM.sub("", k).strip()
    if len(k) < 3 or k.isdigit() or re.search(r"\b(pvt|ltd|limited|llp)\b", k):
        return ""
    if k in MOLECULE_ALIASES:
        return MOLECULE_ALIASES[k]
    changed = True
    while changed:
        changed = False
        for suf in SALT_SUFFIXES:
            if k.endswith(suf) and len(k) > len(suf) + 3:
                k = k[: -len(suf)].strip()
                changed = True
    return MOLECULE_ALIASES.get(k, k)


STRENGTH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mcg|µg|ug|mg|gm|g|ml|iu|%|w/w|w/v|v/v|mmol|meq|lac|lakh|million)?", re.I)


def norm_strength(s: str | None) -> str:
    if not s:
        return ""
    s = ascii_fold(str(s)).lower().replace(" ", "")
    s = s.replace("gm", "g").replace("ug", "mcg").replace("w/w", "%").replace("w/v", "%").replace("v/v", "%")
    s = s.replace("%%", "%")
    return s


COMP_PART = re.compile(r"\s*([^()+]+?)\s*\(([^)]*)\)\s*")


def parse_composition(text: str | None) -> list[tuple[str, str]]:
    """'Amoxycillin (500mg) + Clavulanic Acid (125mg)' -> [('Amoxycillin','500mg'), ...].
    Also handles 'PARACETAMOL-500MG' and bare 'Paracetamol 500mg'."""
    if not text:
        return []
    out = []
    for part in re.split(r"\s\+\s|\+|,(?![^()]*\))", str(text)):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", part)
        if m:
            out.append((m.group(1).strip(), m.group(2).strip()))
            continue
        m = re.match(r"^(.*?)[\s-]+(\d[\d.]*\s*(?:mcg|mg|g|gm|ml|iu|%)[^\s]*)\s*$", part, re.I)
        if m:
            out.append((m.group(1).strip(" -"), m.group(2).strip()))
        else:
            out.append((part, ""))
    return [(n, s) for n, s in out if n and not n.isdigit()]


PACK_QTY = re.compile(
    r"(?:strip|bottle|box|packet|vial|tube|jar|sachet|pack|kit|carton|ampoule|cartridge|pen|bag|can|dropper|container|tin)"
    r"\s+of\s+(\d+(?:\.\d+)?)\s*(tablet|capsule|softgel|ml|gm|g|sachet|unit|piece|lozenge|injection|patch|respule|rotacap|suppositor|pessar|strip|vial|ampoule)?",
    re.I,
)


def pack_quantity(pack: str | None) -> tuple[float | None, str | None]:
    if not pack:
        return None, None
    m = PACK_QTY.search(str(pack))
    if not m:
        return None, None
    q = float(m.group(1))
    unit = (m.group(2) or "").lower() or None
    return (q if q > 0 else None), unit


def fix_mojibake(s: str | None) -> str | None:
    """Undo UTF-8 text that was decoded as Latin-1/CP1252 upstream ('LantusÂ®' -> 'Lantus®')."""
    if not s or not any(ch in s for ch in "ÂÃâ"):
        return s
    for enc in ("cp1252", "latin-1"):
        try:
            return s.encode(enc).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return s
