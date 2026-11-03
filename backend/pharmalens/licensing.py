"""What DrugDen may sell, per dataset. The API and the public samples must only serve data whose class allows it.

Classes (strictest wins when a table mixes sources):
  open        reusable commercially; attribution text should still travel with it
  attribution reusable commercially only with the stated attribution (and stated conditions, e.g. share-alike)
  gazette     published in the Official Gazette of India: reproduction is not infringement (Copyright Act s.52(1)(q)(i));
              serve with the notification reference and source
  permission  government website content whose policy requires permission to reproduce (CDSCO says so explicitly);
              internal and terminal use only until written permission is on file (see PERMISSIONS)
  internal    must not be sold or published: non-commercial licences, scraped e-pharmacy content, licensed market data

Reviewed 2026-10-28 from each source's published terms; docs/LICENSING.md explains every row. Not legal advice:
have a lawyer confirm before launch.
"""

OPEN, ATTRIBUTION, GAZETTE, PERMISSION, INTERNAL = "open", "attribution", "gazette", "permission", "internal"
RANK = {OPEN: 0, ATTRIBUTION: 1, GAZETTE: 1, PERMISSION: 3, INTERNAL: 4}
SELLABLE = {OPEN, ATTRIBUTION, GAZETTE}

# written permissions received (source key -> reference); a 'permission' table becomes sellable once its source is here
PERMISSIONS: dict[str, str] = {}

SOURCES = {
    "cdsco_web":   {"name": "CDSCO websites (cdsco.gov.in, cdscoonline.gov.in)", "class": PERMISSION,
                    "terms": "'The contents of this website may not be reproduced partially or fully, without due permission'; "
                             "source must be acknowledged", "attribution": "Source: CDSCO, Government of India"},
    "nppa_web":    {"name": "NPPA website and IPDMS dashboard", "class": PERMISSION,
                    "terms": "no published reuse policy found; treated like CDSCO until confirmed", "attribution": "Source: NPPA"},
    "gazette":     {"name": "Gazette of India notifications (NPPA price orders, FDC bans, ceiling prices)", "class": GAZETTE,
                    "terms": "Copyright Act 1957 s.52(1)(q)(i)", "attribution": "Source: Gazette of India, S.O. <number>"},
    "state_gov":   {"name": "State medical corporations (RMSCL, TNMSC, HMSCL, UPMSCL), IPC/PvPI, PMBI Jan Aushadhi",
                    "class": PERMISSION, "terms": "government website policies; not individually confirmed",
                    "attribution": "Source: <agency>, Government of <state/India>"},
    "cdci":        {"name": "Common Drug Codes for India (NRCeS, C-DAC)", "class": ATTRIBUTION,
                    "terms": "CC BY 4.0; redistribution and derivatives allowed within India only; brand names are their "
                             "owners' marks; SNOMED CT codes inside fall under the SNOMED affiliate licence",
                    "attribution": "Common Drug Codes for India, NRCeS / C-DAC Pune (CC BY 4.0)"},
    "openfda":     {"name": "openFDA (approvals, Orange Book, NDC, recalls, shortages, labels, FAERS)", "class": OPEN,
                    "terms": "CC0 1.0 public domain unless marked", "attribution": "Source: U.S. FDA (openFDA)"},
    "fda_web":     {"name": "FDA Import Alert 66-40 pages", "class": OPEN, "terms": "U.S. government work",
                    "attribution": "Source: U.S. FDA"},
    "ctgov":       {"name": "ClinicalTrials.gov", "class": ATTRIBUTION,
                    "terms": "NLM data provided free of charge; attribution expected", "attribution": "Source: ClinicalTrials.gov (U.S. NLM)"},
    "ema":         {"name": "European Medicines Agency register", "class": ATTRIBUTION,
                    "terms": "commercial reuse allowed if EMA is acknowledged in each copy", "attribution": "Source: European Medicines Agency"},
    "who":         {"name": "WHO prequalification list and medical product alerts", "class": INTERNAL,
                    "terms": "CC BY-NC-SA 3.0 IGO / not for commercial purposes; commercial use needs WHO permission",
                    "attribution": "Source: World Health Organization"},
    "chembl":      {"name": "ChEMBL (EMBL-EBI)", "class": ATTRIBUTION,
                    "terms": "CC BY-SA 3.0: attribution, and redistributed derivatives of these fields stay CC BY-SA",
                    "attribution": "ChEMBL, EMBL-EBI (CC BY-SA 3.0)"},
    "gdelt":       {"name": "GDELT news index", "class": ATTRIBUTION, "terms": "open for commercial use with citation",
                    "attribution": "The GDELT Project"},
    "news":        {"name": "News headlines (publisher RSS, Google News)", "class": INTERNAL,
                    "terms": "publishers' copyright; show headline + link in the terminal only", "attribution": "<publisher>"},
    "nse":         {"name": "NSE quotes, history, fundamentals, corporate announcements (incl. via Yahoo)", "class": INTERNAL,
                    "terms": "NSE market data is licensed; redistribution needs an NSE data agreement", "attribution": "Source: NSE"},
    "mfr_lists":   {"name": "Manufacturers' statutory price lists (DPCO Form V / GST revision)", "class": ATTRIBUTION,
                    "terms": "price lists every manufacturer must issue and display (DPCO para 24); facts with the "
                             "document cited", "attribution": "Source: <manufacturer> price list (Form V), <date>"},
    "kaggle_nc":   {"name": "1mg-derived Kaggle datasets (2025 MRPs, label text, safety advice, interactions, images)",
                    "class": INTERNAL, "terms": "CC BY-NC-SA 4.0 / unknown / '(c) original authors'; content scraped from "
                                                "e-pharmacies", "attribution": "-"},
    "drugsetu":    {"name": "DrugSetu API (retired trial)", "class": INTERNAL, "terms": "trial API access", "attribution": "-"},
    "drugden":     {"name": "DrugDen's own derived data (matching, events, first-seen dates, analytics)", "class": OPEN,
                    "terms": "our work; aggregates only where inputs are internal", "attribution": "DrugDen"},
}

# table -> (source keys, note). The table's class is the strictest of its sources.
TABLES = {
    "reg_nsq":              (["cdsco_web"], "NSQ / spurious batch lists"),
    "reg_banned_fdc":       (["gazette"], "prohibited FDC notifications (Gazette S.O.)"),
    "reg_approvals":        (["cdsco_web"], "CDSCO approvals"),
    "sec_items":            (["cdsco_web"], "SEC recommendations"),
    "reg_documents":        (["cdsco_web", "nppa_web"], "document index (titles + links)"),
    "brand_registry":       (["cdsco_web"], "Rule 84AB brand registry"),
    "nppa_ceiling":         (["gazette"], "ceiling prices (Gazette); IPDMS copy is a convenience"),
    "nppa_ceiling_history": (["gazette"], "historic ceilings"),
    "nppa_retail_prices":   (["gazette"], "new-drug retail price orders (Gazette S.O.)"),
    "nlem":                 (["gazette"], "NLEM 2022 (notified as DPCO Schedule I)"),
    "jan_aushadhi":         (["state_gov"], "PMBI product and MRP list"),
    "procurement_rates":    (["state_gov"], "state tender rates"),
    "firm_debarments":      (["state_gov"], "UPMSCL blacklisting"),
    "pvpi_alerts":          (["state_gov"], "PvPI drug safety alerts"),
    "cdci_brand":           (["cdci"], ""), "cdci_generic": (["cdci"], ""), "cdci_product": (["cdci"], ""),
    "cdci_substance":       (["cdci"], ""), "cdci_supplier": (["cdci"], ""), "cdci_doseform": (["cdci"], ""),
    "cdci_route":           (["cdci"], ""),
    "us_applications":      (["openfda"], ""), "us_orange_book": (["openfda"], ""), "us_ndc": (["openfda"], ""),
    "us_patents":           (["openfda"], ""), "shortages": (["openfda"], "US shortages"),
    "usfda_actions":        (["openfda", "fda_web"], "recalls + import alerts"),
    "trials":               (["ctgov"], ""),
    "ema_medicines":        (["ema"], ""),
    "who_pq":               (["who"], ""),
    "molecule_enrichment":  (["chembl", "openfda"], "ChEMBL fields are share-alike"),
    "news":                 (["news", "gdelt"], "headlines are publishers' text"),
    "quotes":               (["nse"], ""), "quote_history": (["nse"], ""), "corp_announcements": (["nse"], ""),
    "mfr_prices":           (["mfr_lists"], "manufacturer MRP / PTR / PTS"),
    "brand_first_seen":     (["cdsco_web", "cdci", "drugden"], "first-seen dates are ours; brand rows come from the registries"),
    # catalog: assembled from 17 Kaggle datasets incl. non-commercial and unlicensed ones (their own docs: treat the
    # merged output as non-commercial). Rebuild from permitted sources before selling (docs/LICENSING.md, plan).
    "products":             (["kaggle_nc", "mfr_lists"], "catalog spine"),
    "product_info":         (["kaggle_nc"], "1mg label text"),
    "interactions":         (["kaggle_nc"], "1mg interaction lists"),
    "price_observations":   (["kaggle_nc", "mfr_lists", "drugsetu"], "per-row source column; mfr rows are sellable"),
    "drugsetu_products":    (["drugsetu"], ""),
    "molecules":            (["kaggle_nc", "chembl", "drugden"], "names from the catalog"),
    "product_molecules":    (["kaggle_nc", "drugden"], ""),
    "combos":               (["kaggle_nc", "drugden"], ""),
    "companies":            (["kaggle_nc", "drugden"], "names as written on catalog rows"),
    "parents":              (["drugden"], "our corporate-group map"),
    "segment_share":        (["drugden", "kaggle_nc"], "estimates computed from the catalog: aggregates only"),
    "segment_stats":        (["drugden", "kaggle_nc"], "aggregates only"),
    "events":               (["drugden", "news", "nse", "cdsco_web"], "mixes every feed: internal unless filtered by source"),
    # derived links (Phase 1). Each row also carries its own `licence` (strictest of its inputs), so links built only
    # from open inputs can be released even though the table as a whole mixes classes.
    "entity_links":         (["drugden", "kaggle_nc", "cdsco_web", "openfda", "ctgov", "news", "state_gov", "gazette"],
                             "per-row licence column"),
    "event_entities":       (["drugden", "news", "nse", "cdsco_web"], "per-row licence column"),
    "price_unit_obs":       (["kaggle_nc", "mfr_lists", "drugsetu"], "per-row licence column; mfr rows are sellable"),
    "linker_runs":          (["drugden"], "run log"),
    "launch_signals":       (["cdsco_web", "cdci", "gazette", "drugden"], "per-row licence column"),
    "auto_groups":          (["kaggle_nc", "drugden"], "company names come from the catalog"),
    "molecule_aliases":     (["kaggle_nc", "chembl", "drugden"], "molecule names from the catalog; ChEMBL ids share-alike"),
    "makers":               (["cdsco_web", "openfda", "cdci", "state_gov", "kaggle_nc", "drugden"], "firm names from every source; links carry their own licence"),
    "fda_inspections":      (["fda_web"], "FDA Data Dashboard inspections (classification)"),
    "fda_citations":        (["fda_web"], "FDA Data Dashboard Form 483 citations"),
    "fda_compliance_actions": (["fda_web"], "FDA Data Dashboard compliance actions (warning letters, injunctions)"),
    "fda_import_refusals":  (["fda_web"], "FDA Data Dashboard import refusals (drug shipments from India)"),
    "sites":                (["cdsco_web", "openfda", "state_gov", "drugden"], "addresses from approvals, NSQ lists, US FDA, debarments"),
    "maker_makes_for":      (["cdsco_web", "kaggle_nc", "drugden"], "84AB registrations matched to catalog SKUs"),
}


def source_class(key: str) -> str:
    src = SOURCES[key]
    if src["class"] == PERMISSION and key in PERMISSIONS:
        return ATTRIBUTION
    return src["class"]


def table_class(table: str) -> str:
    """Strictest class among a table's sources; unknown tables are internal."""
    if table not in TABLES:
        return INTERNAL
    return max((source_class(k) for k in TABLES[table][0]), key=RANK.__getitem__)


def sellable(table: str) -> bool:
    return table_class(table) in SELLABLE


def attribution(table: str) -> list[str]:
    return [SOURCES[k]["attribution"] for k in TABLES.get(table, ([], ""))[0] if SOURCES[k]["attribution"] != "-"]


if __name__ == "__main__":
    for cls in (OPEN, ATTRIBUTION, GAZETTE, PERMISSION, INTERNAL):
        names = [t for t in TABLES if table_class(t) == cls]
        print(f"{cls:12s} {len(names):2d}  {', '.join(names)}")
