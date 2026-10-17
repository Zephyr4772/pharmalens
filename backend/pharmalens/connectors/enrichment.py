"""Molecule enrichment: pharmacology, global label text and post-marketing reaction signal.

Per catalog molecule (largest first, then refreshed oldest-first after 45 days):
* ChEMBL     — ATC codes, max clinical phase, first approval year, molecule type, withdrawn / boxed-warning
               flags, mechanisms of action and the indication list (MeSH) with the phase reached for each.
* openFDA    — the most recent single-ingredient US prescribing label (boxed warning, indications,
               contraindications, warnings, adverse reactions, interactions, mechanism, pregnancy, overdose).
* FAERS      — top reported adverse reactions (MedDRA preferred terms) from the US adverse-event system.
               Spontaneous reports: a signal, not incidence.

openFDA allows 1,000 requests/day per IP without a key; OPENFDA_API_KEY (free) raises it to 120,000.
"""
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from .. import db
from ..normalize import molecule_key
from .base import Connector

# Indian (INN / BP) names whose US names differ
US_NAME = {
    "paracetamol": "acetaminophen", "salbutamol": "albuterol", "adrenaline": "epinephrine", "noradrenaline": "norepinephrine",
    "glibenclamide": "glyburide", "frusemide": "furosemide", "lignocaine": "lidocaine", "rifampicin": "rifampin",
    "cyclosporin": "cyclosporine", "ciclosporin": "cyclosporine", "thyroxine": "levothyroxine", "mesalazine": "mesalamine",
    "pethidine": "meperidine", "isoprenaline": "isoproterenol", "phenobarbitone": "phenobarbital", "amoxycillin": "amoxicillin",
    "cephalexin": "cephalexin", "levosalbutamol": "levalbuterol", "dicyclomine": "dicyclomine", "chlorpheniramine": "chlorpheniramine",
    "beclomethasone": "beclomethasone", "colecalciferol": "cholecalciferol", "oestradiol": "estradiol", "ergocalciferol": "ergocalciferol",
    "sodium valproate": "valproate", "valproic acid": "valproic acid",
}
LABEL_FIELDS = {
    "boxed_warning": ["boxed_warning"], "indications": ["indications_and_usage"], "contraindications": ["contraindications"],
    "warnings": ["warnings_and_cautions", "warnings"], "adverse_reactions": ["adverse_reactions"],
    "interactions": ["drug_interactions"], "mechanism": ["mechanism_of_action"],
    "pregnancy": ["pregnancy", "use_in_specific_populations"], "overdosage": ["overdosage"],
}
CHEMBL = "https://www.ebi.ac.uk/chembl/api/data/"
OPENFDA = "https://api.fda.gov/drug/"


BG_LOCK = threading.Lock()
# names that denote a class or mixture in Indian labelling, not one compound
OFFICIAL_SYN = {"INN", "BAN", "USAN", "ATC", "BNF", "DCF", "FDA", "USP", "EMA", "MERCK_INDEX"}
CLASS_NAMES = {"phospholipids", "lecithin", "vitamin k2", "vitamin e", "vitamin b complex", "vitamin a", "multivitamin", "multimineral", "omega 3 fatty acids", "omega 3",
               "fish oil", "lactobacillus", "probiotic", "prebiotic", "antioxidant", "herbal", "ayurvedic", "enzymes", "digestive enzyme",
               "fungal diastase", "pancreatin", "papain", "ginseng", "spirulina", "green tea extract", "grape seed extract", "lycopene"}


class QuotaHit(Exception):
    pass


class MoleculeEnrichment(Connector):
    name = "molecule_enrichment"
    title = "Molecule enrichment (ChEMBL · openFDA label · FAERS)"
    agency = "EMBL-EBI / US FDA"
    schedule = {"trigger": "cron", "hour": "1,7,13,19", "minute": 50}
    description = "ATC, mechanism, indications by phase, US label sections and top reported adverse reactions for each molecule."

    _bg = None

    def run(self):
        key = os.getenv("OPENFDA_API_KEY")
        batch = int(os.getenv("MOLECULE_ENRICH_BATCH") or (4000 if key else 120))
        cur = db.cursor()
        todo = cur.execute("""
            SELECT m.id, m.name FROM molecules m LEFT JOIN molecule_enrichment e ON e.molecule_id = m.id
            WHERE coalesce(m.product_count, 0) >= 3 AND (e.molecule_id IS NULL OR e.fetched_at < now() - INTERVAL 45 DAY)
            ORDER BY e.fetched_at NULLS FIRST, m.product_count DESC LIMIT ?""", [batch]).fetchall()
        self.stats.rows_seen = len(todo)
        hits = {"chembl": 0, "label": 0, "faers": 0}
        self.key = key
        # each molecule is ~6 sequential HTTP calls; fetch several molecules at once, write one at a time.
        # 8 workers stay under openFDA's keyed limit (240 req/min); without a key the daily cap is the limit anyway.
        workers = int(os.getenv("MOLECULE_ENRICH_WORKERS") or (8 if key else 2))
        pool = ThreadPoolExecutor(max_workers=workers)
        futs = {pool.submit(self.enrich, name, key): mid for mid, name in todo}
        for fut in as_completed(futs):
            mid = futs[fut]
            try:
                rec = fut.result()
            except QuotaHit:
                self.stats.notes.append("openFDA daily quota reached; resumes next run")
                for f in futs:
                    f.cancel()
                break
            except Exception as e:  # noqa: BLE001 — one bad molecule must not stop the batch
                self.stats.notes.append(f"{type(e).__name__} on molecule {mid}")
                continue
            for k in hits:
                hits[k] += bool(rec.get(k + "_ok"))
            with db.writer() as w:
                w.execute("""INSERT OR REPLACE INTO molecule_enrichment (molecule_id, chembl_id, atc, max_phase, first_approval, molecule_type,
                                 withdrawn, black_box, mechanisms, indications, faers_top, faers_total, us_label, us_label_meta, us_name,
                                 fetched_at, faers_co, faers_names, chembl_ambiguous)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, now(), ?,?,?)""", [
                    mid, rec.get("chembl_id"), json.dumps(rec.get("atc") or []), rec.get("max_phase"), rec.get("first_approval"),
                    rec.get("molecule_type"), rec.get("withdrawn"), rec.get("black_box"),
                    json.dumps(rec.get("mechanisms") or []), json.dumps(rec.get("indications") or []),
                    json.dumps(rec.get("faers") or []), rec.get("faers_total"), json.dumps(rec.get("label") or {}),
                    rec.get("label_meta") and json.dumps(rec["label_meta"]), rec.get("us_name"),
                    json.dumps(rec.get("faers_co") or []), json.dumps(rec.get("faers_names") or []),
                    rec.get("chembl_ambiguous") and json.dumps(rec["chembl_ambiguous"])])
            self.stats.rows_new += 1
        pool.shutdown(wait=True, cancel_futures=True)
        left = cur.execute("""SELECT count(*) FROM molecules m LEFT JOIN molecule_enrichment e ON e.molecule_id = m.id
                              WHERE coalesce(m.product_count,0) >= 3 AND e.molecule_id IS NULL""").fetchone()[0]
        self.stats.notes.append(f"ChEMBL {hits['chembl']} · label {hits['label']} · FAERS {hits['faers']} of {self.stats.rows_new}; {left:,} molecules not yet enriched")

    # ---- per molecule
    def enrich(self, name: str, key: str | None) -> dict:
        n = name.strip().lower()
        mkey = molecule_key(n)
        us = US_NAME.get(n, n)
        rec: dict = {}
        self.chembl(n, us, rec)
        # openFDA uses US names; ChEMBL's parent pref_name is the USAN for most molecules (acetaminophen, albuterol, glyburide)
        us = (rec.get("parent_name") or us).lower()
        if us.count(",") == 1 and len(us.split(",")[1].split()) == 1:
            us = " ".join(reversed([x.strip() for x in us.split(",")]))   # ChEMBL "sulfadiazine, silver" -> "silver sulfadiazine"
        rec["us_name"] = us if us != n else None
        keys = {mkey, molecule_key(us)} - {None, ""}
        self.label(us, keys, key, rec)
        self.faers(us, keys, key, rec)
        return rec

    def jget(self, url: str, params: dict) -> dict | None:
        if url.startswith(OPENFDA) and getattr(self, "key", None):
            params = {**params, "api_key": self.key}
        for attempt in range(4):
            r = self.get(url, params=params, timeout=90)
            # with a key a 429 is the per-minute throttle: back off and retry; without one it is the daily cap
            if r.status_code != 429 or not getattr(self, "key", None) or attempt == 3:
                break
            time.sleep(20 * (attempt + 1))
        if r.status_code == 429:
            raise QuotaHit
        if r.status_code != 200:
            return None
        return r.json()

    def chembl(self, n: str, us: str, rec: dict):
        if n in CLASS_NAMES:
            rec["chembl_ambiguous"] = ["class name"]
            return
        mol = None
        for q in ({"pref_name__iexact": n}, {"pref_name__iexact": us}, {"molecule_synonyms__molecule_synonym__iexact": n}):
            j = self.jget(CHEMBL + "molecule.json", {**q, "limit": 5})
            hits = (j or {}).get("molecules") or []
            if "molecule_synonyms__molecule_synonym__iexact" in q:
                # only official name types count; "OTHER"/trade-name synonyms map e.g. coconut oil -> emulsifying wax
                hits = [m for m in hits if any(x["molecule_synonym"].lower() == n and x["syn_type"] in OFFICIAL_SYN
                                               for x in m.get("molecule_synonyms") or [])]
            # a synonym shared by several compounds (e.g. "vitamin K2" = MK-4, MK-6, MK-7) is ambiguous: take nothing
            parents = {(m.get("molecule_hierarchy") or {}).get("parent_chembl_id") or m["molecule_chembl_id"] for m in hits}
            if len(parents) == 1:
                mol = hits[0]
                break
            if len(parents) > 1:
                rec["chembl_ambiguous"] = sorted(parents)
                return
        if not mol:
            return
        cid = mol["molecule_chembl_id"]
        parent = (mol.get("molecule_hierarchy") or {}).get("parent_chembl_id") or cid
        pname = mol.get("pref_name")
        scope = "parent_molecule_chembl_id"
        if parent != cid:
            pj = self.jget(CHEMBL + f"molecule/{parent}.json", {})
            parent_name = (pj or {}).get("pref_name")
            if parent_name and molecule_key(parent_name) == molecule_key(pname or ""):
                pname = parent_name          # salt form of the same active (metformin hydrochloride -> metformin)
            else:
                # a different active substance (silver sulfadiazine vs sulfadiazine, polaprezinc vs carnosine,
                # etamsylate vs calcium dobesilate's acid): never pool data across them
                parent, scope = cid, "molecule_chembl_id"
        rec.update(chembl_ok=True, chembl_id=cid, parent_name=pname, atc=mol.get("atc_classifications") or [],
                   max_phase=float(mol["max_phase"]) if mol.get("max_phase") else None, first_approval=mol.get("first_approval"),
                   molecule_type=mol.get("molecule_type"), withdrawn=bool(mol.get("withdrawn_flag")), black_box=bool(mol.get("black_box_warning")))
        mech = self.jget(CHEMBL + "mechanism.json", {scope: parent, "limit": 20}) or {}
        rec["mechanisms"] = [{"moa": m.get("mechanism_of_action"), "action": m.get("action_type"), "target": m.get("target_chembl_id")}
                             for m in mech.get("mechanisms", [])]
        ind = self.jget(CHEMBL + "drug_indication.json", {scope: parent, "limit": 500}) or {}
        best: dict[str, float] = {}
        for i in ind.get("drug_indications", []):
            h = i.get("mesh_heading") or i.get("efo_term")
            ph = float(i.get("max_phase_for_ind") or 0)
            if h and ph > best.get(h, -1):
                best[h] = ph
        rec["indications"] = [{"term": h, "phase": p} for h, p in sorted(best.items(), key=lambda x: (-x[1], x[0]))[:40]]

    def faers_background(self) -> tuple[dict, int | None]:
        """Reaction counts across all of FAERS (fetched once per run) for the PRR denominator."""
        with BG_LOCK:
            if self._bg is None:
                j = self.jget(OPENFDA + "event.json", {"count": "patient.reaction.reactionmeddrapt.exact", "limit": 1000}) or {}
                t = self.jget(OPENFDA + "event.json", {"limit": 1}) or {}
                self._bg = ({r["term"]: r["count"] for r in j.get("results") or []}, ((t.get("meta") or {}).get("results") or {}).get("total"))
            return self._bg

    def exact_names(self, endpoint: str, field: str, us: str, mkey: set) -> list[str]:
        """openFDA generic-name spellings that are this molecule alone (any salt, dose or form wording), never a combination."""
        j = self.jget(OPENFDA + endpoint, {"search": f'{field}:"{us}"', "count": f"{field}.exact", "limit": 1000})
        out = []
        for t in (j or {}).get("results") or []:
            if same_molecule(t["term"], mkey):
                out.append(t["term"])
        return out

    def label(self, us: str, mkey: set, key: str | None, rec: dict):
        names = self.exact_names("label.json", "openfda.generic_name", us, mkey)
        if not names:
            return
        q = " ".join(f'openfda.generic_name.exact:"{x}"' for x in names[:20])
        j = self.jget(OPENFDA + "label.json", {"search": q, "limit": 10, "sort": "effective_time:desc"})
        res = [r for r in (j or {}).get("results") or []
               if same_molecule(((r.get("openfda") or {}).get("generic_name") or [""])[0], mkey)
               and len((r.get("openfda") or {}).get("substance_name") or [None]) == 1]
        if not res:
            return

        def rank(r):
            of = r.get("openfda") or {}
            rx = "HUMAN PRESCRIPTION DRUG" in (of.get("product_type") or [])
            sections = sum(any(r.get(s) for s in srcs) for srcs in LABEL_FIELDS.values())
            return (not rx, -sections, -int(r.get("effective_time") or 0))
        best = sorted(res, key=rank)[0]
        out = {}
        for k, srcs in LABEL_FIELDS.items():
            for s in srcs:
                if best.get(s):
                    out[k] = " ".join(best[s])[:4000]
                    break
        of = best.get("openfda") or {}
        rec.update(label_ok=bool(out), label=out, label_meta={
            "set_id": best.get("set_id"), "effective": best.get("effective_time"), "generic": (of.get("generic_name") or [None])[0],
            "brand": (of.get("brand_name") or [None])[0], "manufacturer": (of.get("manufacturer_name") or [None])[0],
            "product_type": (of.get("product_type") or [None])[0], "substance": (of.get("substance_name") or [None])[0],
            "route": of.get("route"), "url": f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={best.get('set_id')}"})

    def faers(self, us: str, mkey: set, key: str | None, rec: dict):
        # only reports listing a single-ingredient product of this molecule (combination products are excluded)
        names = self.exact_names("event.json", "patient.drug.openfda.generic_name", us, mkey)
        if not names:
            return
        q = " ".join(f'patient.drug.openfda.generic_name.exact:"{x}"' for x in names[:20])
        tot = self.jget(OPENFDA + "event.json", {"search": q, "limit": 1})
        j = self.jget(OPENFDA + "event.json", {"search": q, "count": "patient.reaction.reactionmeddrapt.exact", "limit": 40})
        res = (j or {}).get("results") or []
        drop = {"OFF LABEL USE", "DRUG INEFFECTIVE", "PRODUCT USE IN UNAPPROVED INDICATION", "PRODUCT USE ISSUE", "NO ADVERSE EVENT",
                "INAPPROPRIATE SCHEDULE OF PRODUCT ADMINISTRATION", "WRONG TECHNIQUE IN PRODUCT USAGE PROCESS", "CONDITION AGGRAVATED",
                "INCORRECT DOSE ADMINISTERED", "PRODUCT DOSE OMISSION ISSUE",
                "PRODUCT QUALITY ISSUE"}
        total = ((tot or {}).get("meta") or {}).get("results", {}).get("total")
        bg, bg_total = self.faers_background()
        top = []
        for r in res:
            if r["term"] in drop:
                continue
            prr = None
            if total and bg_total and bg.get(r["term"]):
                # share of this drug's reports carrying the reaction / share of all FAERS reports carrying it
                prr = round((r["count"] / total) / (bg[r["term"]] / bg_total), 2)
            # Evans et al. screening rule: PRR >= 2 with at least 3 reports
            top.append({"term": r["term"].title(), "count": r["count"], "prr": prr, "signal": bool(prr and prr >= 2 and r["count"] >= 3)})
        top = top[:20]
        co = self.jget(OPENFDA + "event.json", {"search": q, "count": "patient.drug.openfda.generic_name.exact", "limit": 60}) or {}
        rec["faers_co"] = [{"drug": c["term"].title(), "share": round(c["count"] / total, 3)}
                           for c in co.get("results") or [] if total and not same_molecule(c["term"], mkey)][:10]
        if top:
            rec.update(faers_ok=True, faers=top, faers_total=total,
                       faers_names=names[:20])


DOSE_FORM = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|µg|g|ml|iu|%|units?)\b|\b(?:tablets?|tab|capsules?|cap|extended[- ]release|delayed[- ]release|"
                       r"er|xr|sr|xl|dr|odt|oral|solution|suspension|injection|injectable|for injection|usp|ip|bp|cream|ointment|gel|"
                       r"topical|ophthalmic|otic|nasal|spray|syrup|powder|film[- ]coated|chewable|liquid|drops?|vial|in|sodium chloride)\b", re.I)
SPLIT = re.compile(r"\band\b|,|/|\+|;|\bwith\b|(?<=[a-z])-(?=[a-z]{4,}\b)", re.I)


def same_molecule(term: str, mkey) -> bool:
    """True when an openFDA generic name is exactly this one molecule (salts and dose/form words ignored)."""
    t = (term or "").lower().replace("hcl", "hydrochloride")
    t = re.sub(r"\(.*?\)", " ", t)
    t = re.sub(r"\s+", " ", DOSE_FORM.sub(" ", t)).strip()   # strip "extended-release" etc. before splitting on hyphens
    if len([x for x in SPLIT.split(t) if x.strip()]) != 1:
        return False
    keys = {mkey} if isinstance(mkey, str) else set(mkey)
    return bool(t) and molecule_key(t) in keys
