"""Roadmap #4: resolve molecule names in six text sources into molecule links.

Uses the catalog's molecule dictionary (matcher: exact n-gram match on normalised names and molecule keys, no
fuzzy matching). Confidence depends on how much of the text the match explains:

  complete   (0.95)  structured generic-name field, every remaining word is a dose, unit, form or salt word
  partial    (0.80)  structured field, but some words are unexplained (another ingredient we don't know, a brand)
  free_text  (0.70)  headline / prose: a molecule name occurs in it; never shown as a fact without the label

Confidence answers "does this record involve this molecule"; the method says whether the record's whole ingredient
set is known (complete) or not (partial), and only complete records are used for ingredient-set comparisons.
In prose, a link is high-confidence only for a distinctive drug name (an ATC code, 8+ letters, sold by 3+
companies, not an everyday word); other prose mentions stay inferred. A molecule that occurs in a single catalog
product (often a brand glued to a salt name) costs 0.15, and in prose it is not linked at all. Regulatory and
quality records (US FDA recalls) only get links from their structured product description, never from prose.
"""
import re

from .. import db, matcher
from ..normalize import molecule_key, norm
from .store import licence_of, replace

# words that may surround a molecule name in a generic-name field without meaning another ingredient
NOISE = set("""
ip bp usp ph eur nf inn mg mcg g gm kg ml l iu w v ww wv vv percent per cent unit units dose doses each contains
tablet tablets tab tabs capsule capsules cap caps injection injections inj infusion syrup suspension solution
cream gel ointment drops drop eye ear nasal oral topical lotion powder granules sachet spray inhaler respules
emulsion paste patch suppository suppositories vial vials ampoule ampoules ampule bottle strip pack kit and with
plus in of for the a an as or sr er xr cr mr dr od ds la xl pr film coated chewable dispersible effervescent
orally disintegrating extended release sustained controlled modified delayed prolonged immediate enteric
sterile concentrate lyophilised lyophilized dry reconstitution diluent water hydrochloride hcl sodium potassium
calcium magnesium maleate mesylate besylate succinate tartrate citrate phosphate sulphate sulfate acetate
dihydrate monohydrate trihydrate hydrate anhydrous bromide chloride fumarate lactate gluconate propionate
dipropionate valerate furoate nitrate hyclate hydrobromide disodium trometamol tromethamine base free micronized
micronised preservative ophthalmic otic dermal vaginal rectal sublingual buccal intravenous intramuscular
subcutaneous iv im sc fixed combination dose fdc kit pre filled prefilled syringe pen cartridge vial single use
liquid forte junior paediatric pediatric adult plain new strength strengths each film coated label class
to equivalent eq from approved excipients excipient colour color colours colors lake sunset yellow red fcf ponceau
quinoline tartrazine caramel erythrosine brilliant blue paraben parabens flavoured flavored flavour flavor used only
export rx count bottles container net wt oz fl gram grams gastro resistant cutaneous conventional orodispersible
liquids creams gels pellets oily diluted inhalation form forms undefined containing contain contains details
compound powdered uncoated soft amp pfs sterilised sterilized disposable size i ii iii iv p s b q d m o t h sp cv am
ls tz nrd x cm inches mm vet bolus
""".split())

# prose names that are drugs but also everyday words in news (batteries, beverages, chemicals, nutrition)
PROSE_STOP = {"lithium", "nicotine", "caffeine", "ethanol", "methanol", "ammonia", "chlorine", "fluoride", "glucose",
              "sucrose", "protein", "collagen", "vitamin", "omega", "melatonin", "cannabis", "morphine", "oxytocin",
              "insulin", "dopamine", "serotonin", "cholesterol", "testosterone", "estrogen", "progesterone", "cortisol"}

SINGLE_PRODUCT_PENALTY = 0.15


def _index():
    matcher._load()
    cur = db.cursor()
    pc = dict(cur.execute("SELECT id, coalesce(product_count, 0) FROM molecules").fetchall())
    atc = {r[0] for r in cur.execute("SELECT molecule_id FROM molecule_enrichment WHERE atc IS NOT NULL").fetchall()}
    cc = dict(cur.execute("SELECT id, coalesce(company_count, 0) FROM molecules").fetchall())
    names = {i: norm(n) for i, n in cur.execute("SELECT id, name FROM molecules").fetchall()}
    return matcher._mol, matcher._mol_maxlen, pc, atc, cc, names


def clean_recall(subject: str) -> str:
    """The product part of a US FDA recall description: no class prefix, NDC, pack counts or manufacturer text."""
    s = re.sub(r"^\s*Class\s+I{1,3}\s*:\s*", "", subject or "")
    s = re.split(r"\b(?:Manufactured|Distributed|Packaged|Marketed|Mfd\.?|Made)\s+(?:for|by)\b|\s—\s", s, maxsplit=1, flags=re.I)[0]
    s = re.sub(r"\(?NDC[^)]*\)?|\bRx\s*only\b|\b\d+[- ]count\b", " ", s, flags=re.I)
    return s


def spans(text: str, mol: dict, maxlen: int) -> tuple[list[tuple[int, str]], list[str]]:
    """(matches as (molecule id, matched words), unexplained words). Same walk as matcher.molecules_in."""
    toks = norm(text).split()
    found, left, i = [], [], 0
    while i < len(toks):
        hit = None
        for n in range(min(maxlen, 5, len(toks) - i), 0, -1):
            cand = " ".join(toks[i:i + n])
            if n == 1 and (cand in matcher.MOLECULE_STOP or len(cand) < 5):
                continue
            k = molecule_key(cand)
            mid = mol.get(cand) or (mol.get(k) if k else None)
            if mid and all(w in NOISE for w in cand.split()):
                mid = None        # "Chloride", "Sodium", "Hydrochloride" exist as catalog molecules but are salt words
            if mid:
                hit = (mid, n, cand)
                break
        if hit:
            if hit[0] not in [f[0] for f in found]:
                found.append((hit[0], hit[2]))
            i += hit[1]
        else:
            t = toks[i]
            if t not in NOISE and not re.fullmatch(r"[\d.]+[a-z%]*|[a-z]?\d[\d.]*|%", t):
                left.append(t)
            i += 1
    return found, left


def resolve(text: str, structured: bool, idx) -> list[tuple[int, str, float, str]]:
    """[(molecule id, method, confidence, evidence)]"""
    mol, maxlen, pc = idx[0], idx[1], idx[2]
    if not text or not text.strip():
        return []
    found, left = spans(text, mol, maxlen)
    out = []
    # a common excipient next to other actives is a listed inactive ingredient (colour, base, buffer), not an active;
    # on its own it is the active ("Dextrose Injection", "Zinc Oxide Cream")
    exc = {mid for mid, words in found if words in matcher.EXCIPIENTS or idx[5].get(mid, "") in matcher.EXCIPIENTS}
    others = len(found) > len(exc)
    for mid, words in found:
        if structured and mid in exc and others:
            out.append((mid, "excipient_like", 0.6, f"'{words}' in “{text.strip()[:160]}” (listed with other actives: likely an inactive ingredient)"))
            continue
        single = pc.get(mid, 0) <= 1
        if structured:
            method, conf = ("complete", 0.95) if not left else ("partial", 0.85)
        else:
            if single or len(words) < 6:
                continue          # in prose, short or one-product names collide with ordinary words and brands
            distinctive = (mid in idx[3] and len(words) >= 8 and words not in PROSE_STOP and idx[4].get(mid, 0) >= 3)
            method, conf = ("free_text_drug", 0.85) if distinctive else ("free_text", 0.70)
        if single:
            conf -= SINGLE_PRODUCT_PENALTY
        ev = f"'{words}' in “{text.strip()[:160]}”" + (f"; unexplained: {' '.join(left[:6])}" if left and structured else "")
        out.append((mid, method, round(conf, 2), ev))
    return out


def _run(linker: str, table: str, rows, structured: bool, idx, prefix: str = "") -> dict:
    cache: dict[str, list] = {}
    links = []
    lic = licence_of(table, "molecules")
    for key, text in rows:
        if text is None:
            continue
        if text not in cache:
            cache[text] = resolve(text, structured, idx)
        for mid, method, conf, ev in cache[text]:
            links.append({"src_table": table, "src_key": f"{prefix}{key}", "dst_type": "molecule", "dst_id": mid,
                          "method": f"dict_{method}", "confidence": conf, "evidence": ev, "licence": lic})
    return replace(linker, links, note=f"{len(cache):,} distinct texts")


def run() -> list[dict]:
    idx = _index()
    cur = db.cursor()
    out = [
        _run("mol:brand_registry", "brand_registry",
             cur.execute("""SELECT coalesce(license_number, '') || '|' || coalesce(brand_norm, '') || '|' || coalesce(firm_name, '')
                                   || '|' || md5(coalesce(generic_name, '')), generic_name FROM brand_registry""").fetchall(), True, idx),
        _run("mol:brand_first_seen", "brand_first_seen",
             cur.execute("SELECT source || '|' || key, generic FROM brand_first_seen WHERE generic IS NOT NULL").fetchall(), True, idx),
        # recalls describe the product; import-alert subjects are plant addresses and carry no drug name
        _run("mol:usfda_actions", "usfda_actions",
             [(i, clean_recall(sj)) for i, sj in cur.execute("SELECT id, subject FROM usfda_actions WHERE kind = 'recall'").fetchall()],
             True, idx),
        # interventions are a structured list ("Rifampicin (RIF); Placebo"): resolve each entry on its own
        _run("mol:trials", "trials",
             [(nct, part) for nct, iv in cur.execute("SELECT nct_id, interventions FROM trials WHERE interventions IS NOT NULL").fetchall()
              for part in re.split(r";", iv) if part.strip()], True, idx),
        _run("mol:news", "news", cur.execute("SELECT id, title FROM news").fetchall(), False, idx),
        _run("mol:procurement_rates", "procurement_rates",
             cur.execute("""SELECT buyer || '|' || coalesce(tender_no, '') || '|' || coalesce(item_code, '') || '|' || coalesce(supplier, '')
                                   || '|' || coalesce(unit, '') || '|' || coalesce(level, '') || '|' || coalesce(CAST(rate AS VARCHAR), ''), item
                            FROM procurement_rates""").fetchall(), True, idx),
    ]
    return out
