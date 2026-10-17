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
from datetime import datetime

from .. import db
from .base import Connector

# Indian (INN / BP) names whose US names differ
US_NAME = {
    "paracetamol": "acetaminophen", "salbutamol": "albuterol", "adrenaline": "epinephrine", "noradrenaline": "norepinephrine",
    "glibenclamide": "glyburide", "frusemide": "furosemide", "lignocaine": "lidocaine", "rifampicin": "rifampin",
    "cyclosporin": "cyclosporine", "ciclosporin": "cyclosporine", "thyroxine": "levothyroxine", "mesalazine": "mesalamine",
    "pethidine": "meperidine", "isoprenaline": "isoproterenol", "phenobarbitone": "phenobarbital", "amoxycillin": "amoxicillin",
    "cephalexin": "cephalexin", "levosalbutamol": "levalbuterol", "dicyclomine": "dicyclomine", "chlorpheniramine": "chlorpheniramine",
    "beclomethasone": "beclomethasone", "colecalciferol": "cholecalciferol", "oestradiol": "estradiol", "ergocalciferol": "ergocalciferol",
    "sodium valproate": "valproate", "valproic acid": "valproic acid", "hyoscine butylbromide": "scopolamine", "bupivacaine": "bupivacaine",
}
LABEL_FIELDS = {
    "boxed_warning": ["boxed_warning"], "indications": ["indications_and_usage"], "contraindications": ["contraindications"],
    "warnings": ["warnings_and_cautions", "warnings"], "adverse_reactions": ["adverse_reactions"],
    "interactions": ["drug_interactions"], "mechanism": ["mechanism_of_action"],
    "pregnancy": ["pregnancy", "use_in_specific_populations"], "overdosage": ["overdosage"],
}
CHEMBL = "https://www.ebi.ac.uk/chembl/api/data/"
OPENFDA = "https://api.fda.gov/drug/"


class QuotaHit(Exception):
    pass


class MoleculeEnrichment(Connector):
    name = "molecule_enrichment"
    title = "Molecule enrichment (ChEMBL · openFDA label · FAERS)"
    agency = "EMBL-EBI / US FDA"
    schedule = {"trigger": "cron", "hour": "1,7,13,19", "minute": 50}
    description = "ATC, mechanism, indications by phase, US label sections and top reported adverse reactions for each molecule."

    def run(self):
        key = os.getenv("OPENFDA_API_KEY")
        batch = int(os.getenv("MOLECULE_ENRICH_BATCH") or (1500 if key else 120))
        cur = db.cursor()
        todo = cur.execute("""
            SELECT m.id, m.name FROM molecules m LEFT JOIN molecule_enrichment e ON e.molecule_id = m.id
            WHERE coalesce(m.product_count, 0) >= 3 AND (e.molecule_id IS NULL OR e.fetched_at < now() - INTERVAL 45 DAY)
            ORDER BY e.fetched_at NULLS FIRST, m.product_count DESC LIMIT ?""", [batch]).fetchall()
        self.stats.rows_seen = len(todo)
        hits = {"chembl": 0, "label": 0, "faers": 0}
        for mid, name in todo:
            try:
                rec = self.enrich(name, key)
            except QuotaHit:
                self.stats.notes.append("openFDA daily quota reached; resumes next run")
                break
            for k in hits:
                hits[k] += bool(rec.get(k + "_ok"))
            with db.writer() as w:
                w.execute("INSERT OR REPLACE INTO molecule_enrichment VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, now())", [
                    mid, rec.get("chembl_id"), json.dumps(rec.get("atc") or []), rec.get("max_phase"), rec.get("first_approval"),
                    rec.get("molecule_type"), rec.get("withdrawn"), rec.get("black_box"),
                    json.dumps(rec.get("mechanisms") or []), json.dumps(rec.get("indications") or []),
                    json.dumps(rec.get("faers") or []), rec.get("faers_total"), json.dumps(rec.get("label") or {}),
                    rec.get("label_meta") and json.dumps(rec["label_meta"]), rec.get("us_name")])
            self.stats.rows_new += 1
        left = cur.execute("""SELECT count(*) FROM molecules m LEFT JOIN molecule_enrichment e ON e.molecule_id = m.id
                              WHERE coalesce(m.product_count,0) >= 3 AND e.molecule_id IS NULL""").fetchone()[0]
        self.stats.notes.append(f"ChEMBL {hits['chembl']} · label {hits['label']} · FAERS {hits['faers']} of {self.stats.rows_new}; {left:,} molecules not yet enriched")

    # ---- per molecule
    def enrich(self, name: str, key: str | None) -> dict:
        n = name.strip().lower()
        us = US_NAME.get(n, n)
        rec: dict = {"us_name": us if us != n else None}
        self.chembl(n, us, rec)
        self.label(us, key, rec)
        self.faers(us, key, rec)
        return rec

    def jget(self, url: str, params: dict) -> dict | None:
        r = self.get(url, params=params, timeout=60)
        if r.status_code == 429:
            raise QuotaHit
        if r.status_code != 200:
            return None
        return r.json()

    def chembl(self, n: str, us: str, rec: dict):
        mol = None
        for q in ({"pref_name__iexact": n}, {"pref_name__iexact": us}, {"molecule_synonyms__molecule_synonym__iexact": n}):
            j = self.jget(CHEMBL + "molecule.json", {**q, "limit": 5})
            if j and j.get("molecules"):
                mol = j["molecules"][0]
                break
        if not mol:
            return
        cid = mol["molecule_chembl_id"]
        parent = (mol.get("molecule_hierarchy") or {}).get("parent_chembl_id") or cid
        rec.update(chembl_ok=True, chembl_id=cid, atc=mol.get("atc_classifications") or [],
                   max_phase=float(mol["max_phase"]) if mol.get("max_phase") else None, first_approval=mol.get("first_approval"),
                   molecule_type=mol.get("molecule_type"), withdrawn=bool(mol.get("withdrawn_flag")), black_box=bool(mol.get("black_box_warning")))
        mech = self.jget(CHEMBL + "mechanism.json", {"parent_molecule_chembl_id": parent, "limit": 20}) or {}
        rec["mechanisms"] = [{"moa": m.get("mechanism_of_action"), "action": m.get("action_type"), "target": m.get("target_chembl_id")}
                             for m in mech.get("mechanisms", [])]
        ind = self.jget(CHEMBL + "drug_indication.json", {"parent_molecule_chembl_id": parent, "limit": 200}) or {}
        best: dict[str, float] = {}
        for i in ind.get("drug_indications", []):
            h = i.get("mesh_heading") or i.get("efo_term")
            ph = float(i.get("max_phase_for_ind") or 0)
            if h and ph > best.get(h, -1):
                best[h] = ph
        rec["indications"] = [{"term": h, "phase": p} for h, p in sorted(best.items(), key=lambda x: (-x[1], x[0]))[:40]]

    def label(self, us: str, key: str | None, rec: dict):
        p = {"search": f'openfda.generic_name:"{us}"', "limit": 8}
        if key:
            p["api_key"] = key
        j = self.jget(OPENFDA + "label.json", p)
        res = (j or {}).get("results") or []

        def rank(r):
            g = ((r.get("openfda") or {}).get("generic_name") or [""])[0].lower()
            sections = sum(any(r.get(s) for s in srcs) for srcs in LABEL_FIELDS.values())
            return (g.count(" and ") + g.count(","), us not in g, -sections, -int(r.get("effective_time") or 0))
        if not res:
            return
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
            "route": of.get("route"), "url": f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={best.get('set_id')}"})

    def faers(self, us: str, key: str | None, rec: dict):
        p = {"search": f'patient.drug.openfda.generic_name:"{us}"', "count": "patient.reaction.reactionmeddrapt.exact", "limit": 25}
        if key:
            p["api_key"] = key
        j = self.jget(OPENFDA + "event.json", p)
        res = (j or {}).get("results") or []
        drop = {"OFF LABEL USE", "DRUG INEFFECTIVE", "PRODUCT USE IN UNAPPROVED INDICATION", "PRODUCT USE ISSUE", "NO ADVERSE EVENT",
                "INAPPROPRIATE SCHEDULE OF PRODUCT ADMINISTRATION", "WRONG TECHNIQUE IN PRODUCT USAGE PROCESS", "CONDITION AGGRAVATED"}
        top = [{"term": r["term"].title(), "count": r["count"]} for r in res if r["term"] not in drop][:20]
        if top:
            rec.update(faers_ok=True, faers=top, faers_total=None)
