"""Molecule hygiene: alias links that fold duplicate, misspelt and brand-glued molecule nodes onto one canonical
molecule (molecule_aliases). The molecules and product_molecules tables are never changed; linkers and pages read
the alias map (canon_map) instead, and dropping molecule_aliases reverts everything.

Applied automatically (deterministic rules, confidence >= 0.85):
  shared_chembl   both molecules carry the same unambiguous ChEMBL id ("Lidocaine" / "Lignocaine")      0.9
  synonym         a curated BAN/INN/USAN synonym pair ("Frusemide" / "Furosemide")                       0.95
  combined_name   the name is two synonyms of one molecule ("Paracetamol Acetaminophen")                 0.95
  rekeyed         today's molecule normaliser gives the name another molecule's key (glued company
                  text and salt words removed: "Ceutical Ltdlidocaine" -> lidocaine)                      0.9
  form_words      only form / route / strength / release words differ ("Clotrimazole Topical",
                  "Metformin Hydrochloride 500 Sr", "Clavulanic Acids")                                   0.9
  acid_anion      "-ate" or bare "-ic" name of an "-ic acid" molecule ("Clavulanate" -> Clavulanic Acid)  0.85
  glued_prefix    a one-to-three-product name that ends in another molecule glued to company-like text
                  ("Cardiwin Life Caremetformin")                                                         0.85
Review only (never applied until accepted in seed/molecule_aliases.csv):
  glued_prefix_unsure  the same, without company-like text                                               0.7
  typo            edit distance <= 2 from a molecule with 10x the products ("Cholecalceferol")           0.7
seed/molecule_aliases.csv (alias_id, canonical_id, decision accept|reject, note) overrides everything: accept
applies a pair at 1.0, reject removes it.
"""
import csv
import re
from collections import defaultdict

import pandas as pd
from rapidfuzz.distance import Levenshtein

from .. import db
from ..config import SEED_DIR
from ..normalize import molecule_key, norm
from .molecules import NOISE
from .store import HIGH, ensure, licence_of

SEED = SEED_DIR / "molecule_aliases.csv"

# British / Indian Pharmacopoeia names and their INN / USAN equivalents (both directions are the same molecule)
SYNONYMS = [("frusemide", "furosemide"), ("lignocaine", "lidocaine"), ("adrenaline", "epinephrine"), ("noradrenaline", "norepinephrine"),
            ("paracetamol", "acetaminophen"), ("salbutamol", "albuterol"), ("glibenclamide", "glyburide"), ("rifampicin", "rifampin"),
            ("chlorpheniramine", "chlorphenamine"), ("dicyclomine", "dicycloverine"), ("thyroxine", "levothyroxine"),
            ("beclomethasone", "beclometasone"), ("cyclosporin", "ciclosporin"), ("cyclosporine", "ciclosporin"), ("oestradiol", "estradiol"),
            ("mesalazine", "mesalamine"), ("aciclovir", "acyclovir"), ("valaciclovir", "valacyclovir"), ("cephalexin", "cefalexin"),
            ("amoxycillin", "amoxicillin"), ("phenobarbitone", "phenobarbital"), ("dothiepin", "dosulepin"), ("ethamsylate", "etamsylate"),
            ("torsemide", "torasemide"), ("chlorthalidone", "chlortalidone"), ("trimeprazine", "alimemazine"), ("sodium cromoglycate", "cromolyn sodium"),
            ("glyceryl trinitrate", "nitroglycerin"), ("isoprenaline", "isoproterenol"), ("lysine acetylsalicylate", "aspirin dl lysine"),
            ("aspirin", "acetylsalicylic acid"), ("dextrose", "glucose"), ("liquid paraffin", "mineral oil"), ("dimethicone", "dimeticone"),
            ("leuprolide", "leuprorelin"), ("colecalciferol", "cholecalciferol"), ("ergocalciferol", "calciferol"), ("rutin", "rutoside"),
            ("busulphan", "busulfan"), ("cephradine", "cefradine"), ("cephazolin", "cefazolin"), ("sulphasalazine", "sulfasalazine"),
            ("sulphamethoxazole", "sulfamethoxazole"), ("sulphadiazine", "sulfadiazine"), ("indomethacin", "indometacin"),
            ("methotrimeprazine", "levomepromazine"), ("pethidine", "meperidine"), ("hyoscine butylbromide", "butylscopolamine"),
            ("oxethazaine", "oxetacaine"), ("dibucaine", "cinchocaine"), ("ormeloxifene", "centchroman"), ("carbamide", "urea")]
CHEM_PREFIX = {"levo", "dex", "es", "ar", "nor", "des", "iso", "di", "tri", "tetra", "hydroxy", "methyl", "ethyl", "oxy", "chloro", "fluoro",
               "bromo", "nitro", "amino", "acetyl", "pro", "pre", "meth", "eth", "but", "prop", "s", "r", "l", "d", "dl"}
COMPANYISH = re.compile(r"(ltd|limited|private|pvt|pharma|pharmacy|care|labs?|ceutical|health|life|bio|remed|gen|med|cure)", re.I)
# ester / salt words that change the drug (fluticasone furoate != fluticasone propionate): pairs that differ here are
# never applied automatically, whatever the rule
ESTERS = {"propionate", "dipropionate", "furoate", "valerate", "acetonide", "butyrate", "acetate", "diacetate", "hemisuccinate",
          "succinate", "palmitate", "decanoate", "enanthate", "undecanoate", "cypionate", "benzoate", "phosphate", "pivalate",
          "aceponate", "fumarate", "hyclate", "lysinate", "tosilate", "mofetil", "medoxomil", "axetil", "proxetil", "pivoxil",
          "alafenamide", "disoproxil", "etexilate", "marboxil", "cilexetil", "mesylate", "bromide", "nitrate"}
RELEASE = re.compile(r"(?<=[a-z]{5})(sr|er|xr|cr|mr|od|ds|dt|md)$")


# words _strip may drop: form / route / strength / release words, never letters (vitamin D != vitamin A)
STRIP = {w for w in NOISE if len(w) >= 3 and w not in {"iii", "ii", "iv"}}
# what is left after stripping must not be a bare mineral or element: zinc chloride is not "zinc"
MINERALS = {"zinc", "iron", "calcium", "magnesium", "sodium", "potassium", "copper", "selenium", "chromium", "manganese",
            "aluminium", "aluminum", "silver", "lithium", "ferrous", "ferric", "elemental", "iodine", "boron", "molybdenum", "cobalt"}
CHIRAL = {"s", "r", "levo", "dextro", "dex", "rs"}


def _strip(name: str) -> str:
    toks = [t for t in norm(name).split() if t not in STRIP and not re.fullmatch(r"[\d.]+[a-z%]*|%", t)]
    toks = [RELEASE.sub("", t) for t in toks]
    toks = ["acid" if t == "acids" else t for t in toks]
    return " ".join(t for t in toks if t)


def candidates(cur) -> list[dict]:
    mols = cur.execute("""SELECT m.id, m.name, m.mkey, coalesce(m.product_count, 0), e.chembl_id, coalesce(e.chembl_ambiguous, false), e.atc
                          FROM molecules m LEFT JOIN molecule_enrichment e ON e.molecule_id = m.id""").fetchall()
    pc = {m[0]: m[3] for m in mols}
    name = {m[0]: m[1] for m in mols}
    by_key: dict[str, list[int]] = defaultdict(list)
    by_norm: dict[str, list[int]] = defaultdict(list)
    for mid, nm, mk, *_ in mols:
        by_key[mk].append(mid)
        by_norm[norm(nm)].append(mid)

    def lookup(text: str) -> list[int]:
        k = molecule_key(text)
        return by_key.get(k, []) + by_norm.get(norm(text), []) + (by_key.get(k, []) if k != text else [])

    out = []

    def esters(i):
        return {t for t in norm(name[i]).split() if t in ESTERS}

    def chiral(i):
        t = norm(name[i]).split()
        return t[0] if t and t[0] in CHIRAL else ""

    def add(a, b, method, conf, ev):
        if a != b and a in pc and b in pc:
            if chiral(a) != chiral(b) and method not in ("synonym", "shared_chembl"):
                method, conf, ev = method + "_chirality_differs", 0.7, ev + " (but a chirality prefix differs: may be a different drug)"
            ea, eb = esters(a), esters(b)
            if ea and eb and ea != eb and conf >= HIGH and method not in ("synonym", "shared_chembl"):
                method, conf, ev = method + "_ester_differs", 0.7, ev + f" (but {'/'.join(ea)} vs {'/'.join(eb)}: different ester or salt)"
            out.append({"a": a, "b": b, "method": method, "confidence": conf, "evidence": ev})

    # shared unambiguous ChEMBL id
    chembl: dict[str, list[int]] = defaultdict(list)
    for mid, nm, mk, p, ch, amb, atc in mols:
        if ch and not amb:
            chembl[ch].append(mid)
    for ch, ids in chembl.items():
        for b in ids[1:]:
            add(b, ids[0], "shared_chembl", 0.9, f"'{name[b]}' and '{name[ids[0]]}' share {ch}")
    # curated synonyms and names made of two synonyms
    for x, y in SYNONYMS:
        for a in by_key.get(molecule_key(x), []) + by_norm.get(x, []):
            for b in by_key.get(molecule_key(y), []) + by_norm.get(y, []):
                add(a, b, "synonym", 0.95, f"'{name[a]}' = '{name[b]}' (BAN/INN synonym)")
    syn = {molecule_key(x): molecule_key(y) for x, y in SYNONYMS} | {molecule_key(y): molecule_key(x) for x, y in SYNONYMS}
    for mid, nm, mk, p, *_ in mols:
        toks = norm(nm).split()
        for i in range(1, len(toks)):
            l, r = molecule_key(" ".join(toks[:i])), molecule_key(" ".join(toks[i:]))
            if l and r and (syn.get(l) == r or l == r):
                for b in by_key.get(l, []):
                    add(mid, b, "combined_name", 0.95, f"'{nm}' = '{' '.join(toks[:i])}' + its synonym '{' '.join(toks[i:])}'")
    for mid, nm, mk, p, *_ in mols:
        # today's normaliser (glued company text, salt words, curated aliases)
        k = molecule_key(nm)
        if k and k != mk and not set(k.split()) <= MINERALS:
            for b in by_key.get(k, []):
                add(mid, b, "rekeyed", 0.9, f"'{nm}' normalises to '{k}', the key of '{name[b]}'")
        # form / route / strength / release words
        s = _strip(nm)
        if s and s != norm(nm) and not set(s.split()) <= MINERALS:
            for b in set(by_norm.get(s, []) + by_key.get(molecule_key(s), [])):
                add(mid, b, "form_words", 0.9, f"'{nm}' without form/strength words is '{s}' = '{name[b]}'")
        # "-ate" / bare "-ic" -> "-ic acid"
        n = norm(nm)
        if re.fullmatch(r"[a-z]{5,}ate", n) or re.fullmatch(r"[a-z]{5,}ic", n):
            stem = n[:-3] if n.endswith("ate") else n[:-2]
            for b in by_norm.get(stem + "ic acid", []):
                add(mid, b, "acid_anion", 0.85, f"'{nm}' is the anion / short form of '{name[b]}'")
        # brand or company text glued onto a molecule ("Cardiwin Life Caremetformin")
        if p <= 3:
            toks = n.split()
            last = toks[-1] if toks else ""
            for cut in range(1, len(last) - 6):
                tail = last[cut:]
                hit = by_key.get(tail) or by_norm.get(tail)
                if not hit:
                    continue
                head = " ".join(toks[:-1] + [last[:cut]])
                if last[:cut] in CHEM_PREFIX or any(last[:cut].endswith(cp) and len(last[:cut]) <= len(cp) + 1 for cp in ("levo", "dex", "nor", "des")):
                    break
                sure = bool(COMPANYISH.search(head))
                for b in hit:
                    add(mid, b, "glued_prefix" if sure else "glued_prefix_unsure", 0.85 if sure else 0.7,
                        f"'{nm}' = '{head}' glued to '{name[b]}'")
                break
    # a bare name that would join molecules with different esters ("Fluticasone": furoate or propionate) is ambiguous
    targets: dict[int, set] = defaultdict(set)
    for c in out:
        if c["confidence"] >= HIGH and c["method"] not in ("synonym", "shared_chembl"):
            for bare, other in ((c["a"], c["b"]), (c["b"], c["a"])):
                if not esters(bare) and esters(other):
                    targets[bare].add(frozenset(esters(other)))
    for c in out:
        amb = [x for x in (c["a"], c["b"]) if len(targets.get(x, set())) >= 2]
        if c["confidence"] >= HIGH and amb and c["method"] not in ("synonym", "shared_chembl"):
            c["method"], c["confidence"] = c["method"] + "_ambiguous_ester", 0.7
            c["evidence"] += f" (but '{name[amb[0]]}' also matches molecules with other esters or salts)"
    # typos (review only)
    big = [(mid, norm(nm), p) for mid, nm, mk, p, *_ in mols if p >= 10 and len(norm(nm)) >= 8]
    small = [(mid, norm(nm), p, atc) for mid, nm, mk, p, ch, amb, atc in mols
             if p <= 50 and len(norm(nm)) >= 8 and not re.search(r"\d|vitamin", norm(nm))]
    atc_of = {m[0]: m[6] for m in mols}
    by_prefix: dict[str, list] = defaultdict(list)
    for b in big:
        by_prefix[b[1][:4]].append(b)
    for mid, n, p, atc in small:
        for b, bn, bp in by_prefix.get(n[:4], []):
            limit = 1 if len(n) < 12 else 2
            if b != mid and bp >= 10 * max(p, 1) and Levenshtein.distance(n, bn) <= limit and not re.search(r"\d|vitamin", bn)                     and not (atc and atc_of.get(b) and atc != atc_of.get(b)):
                add(mid, b, "typo", 0.7, f"'{name[mid]}' is {Levenshtein.distance(n, bn)} letters from '{name[b]}' ({bp} vs {p} products)")
    return out


def _seed() -> dict[tuple[int, int], tuple[str, str]]:
    if not SEED.exists():
        return {}
    out = {}
    with open(SEED, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("alias_id") and r.get("canonical_id") and r.get("decision") in ("accept", "reject"):
                out[(int(r["alias_id"]), int(r["canonical_id"]))] = (r["decision"], r.get("note", ""))
    return out


def run() -> dict:
    ensure()
    with db.writer() as w:
        w.execute("""CREATE TABLE IF NOT EXISTS molecule_aliases (
                       alias_id INTEGER, canonical_id INTEGER, method VARCHAR, confidence DOUBLE, evidence VARCHAR,
                       applied BOOLEAN, licence VARCHAR, PRIMARY KEY (alias_id, canonical_id, method))""")
    cur = db.cursor()
    pc = dict(cur.execute("SELECT id, coalesce(product_count, 0) FROM molecules").fetchall())
    seed = _seed()
    cands = candidates(cur)
    for (a, b), (dec, note) in seed.items():
        if dec == "accept":
            cands.append({"a": a, "b": b, "method": "reviewed", "confidence": 1.0, "evidence": f"accepted in seed/molecule_aliases.csv {note}".strip()})
    rejected = {frozenset(k) for k, (d, _) in seed.items() if d == "reject"}
    # union-find over applied pairs; the canonical is the member with the most products
    parent: dict[int, int] = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    nm = dict(cur.execute("SELECT id, name FROM molecules").fetchall())
    comp_esters: dict[int, set] = {}

    def est(x):
        return comp_esters.setdefault(x, {t for t in norm(nm.get(x, "")).split() if t in ESTERS})

    blocked = set()
    # strongest evidence first, so a bare name ("Fluticasone") joins the group its best evidence points to
    for c in sorted(cands, key=lambda c: -c["confidence"]):
        if c["confidence"] >= HIGH and frozenset((c["a"], c["b"])) not in rejected:
            ra, rb = find(c["a"]), find(c["b"])
            if ra == rb:
                continue
            ea, eb = est(ra), est(rb)
            if ea and eb and ea != eb and c["method"] not in ("synonym", "shared_chembl", "reviewed"):
                blocked.add((c["a"], c["b"], c["method"]))   # e.g. fluticasone furoate vs propionate via bare "fluticasone"
                continue
            keep, drop = (ra, rb) if (pc.get(ra, 0), -ra) >= (pc.get(rb, 0), -rb) else (rb, ra)
            parent[drop] = keep
            comp_esters[keep] = est(keep) | est(drop)
    canon = {x: find(x) for x in {c["a"] for c in cands} | {c["b"] for c in cands}}
    lic = licence_of("molecules", "molecule_enrichment")
    rows = []
    for c in cands:
        applied = (c["confidence"] >= HIGH and frozenset((c["a"], c["b"])) not in rejected
                   and (c["a"], c["b"], c["method"]) not in blocked and canon.get(c["a"], c["a"]) == canon.get(c["b"], c["b"]))
        root = canon.get(c["a"], c["a"]) if applied else c["b"]
        for alias in ([c["a"], c["b"]] if applied else [c["a"]]):
            if alias != root:
                rows.append({"alias_id": alias, "canonical_id": root, "method": c["method"], "confidence": c["confidence"],
                             "evidence": c["evidence"], "applied": applied, "licence": lic})
    df = pd.DataFrame(rows).drop_duplicates(["alias_id", "canonical_id", "method"])
    with db.writer() as w:
        w.execute("DELETE FROM molecule_aliases")
        if len(df):
            w.register("_a", df)
            w.execute("INSERT INTO molecule_aliases SELECT alias_id::INTEGER, canonical_id::INTEGER, method, confidence, evidence, applied, licence FROM _a")
            w.unregister("_a")
        applied = w.execute("SELECT count(DISTINCT alias_id) FROM molecule_aliases WHERE applied").fetchone()[0]
        pending = w.execute("SELECT count(DISTINCT alias_id) FROM molecule_aliases WHERE NOT applied").fetchone()[0]
        w.execute("INSERT INTO linker_runs VALUES ('hygiene', now(), now(), ?, ?, ?)", [len(df), applied, f"{pending} pending review"])
    return {"linker": "hygiene", "links": len(df), "high": applied, "pending_review": pending}


def canon_map() -> dict[int, int]:
    """alias molecule id -> canonical molecule id (applied aliases only). Empty before the first run."""
    try:
        return dict(db.cursor().execute("SELECT DISTINCT alias_id, canonical_id FROM molecule_aliases WHERE applied").fetchall())
    except Exception:  # noqa: BLE001
        return {}


def canon_ids(ids, cmap: dict[int, int]) -> list[str]:
    """Canonical, sorted, de-duplicated molecule ids (as strings) for an ingredient set."""
    return sorted({str(cmap.get(int(i), int(i))) for i in ids if str(i).strip()}, key=int)
