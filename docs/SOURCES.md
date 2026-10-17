# Source registry

Surveyed and wired 2026-10-17. Every source below was probed live. "Status" is what PharmaLens does with it.
Raw responses are archived under `data/lake/<source>/<date>/` before any parsing (connector-specific
archives under `data/raw/<connector>/` predate the lake).

## Tier 1 — official Indian regulators (integrity anchors)

| Source | What it holds | Freshness | Access | Status |
|---|---|---|---|---|
| CDSCO NSQ/spurious portal (`cdscoonline.gov.in/CDSCO/viewPublicNSQDrug`) | Every Not-of-Standard-Quality and spurious batch, central + state labs, structured | 2019 → Aug 2026, monthly | JSON (`reportingYears`, `publicReportingMonths`, `filteredNsqDrugTable`, `filteredSpuriousDrugTable`) | **ingesting** — replaces PDF parsing and the Health Master mirror |
| CDSCO approvals DB (`cdscoonline.gov.in/CDSCO/cdscoDrugs`) | Every approval: drug, composition, dosage, indication, applicant, all manufacturing sites, division (new drug / SND / biological / FDC), date | 2018 → today (latest 14 Oct 2026) | JSON (`loadDrugApprovals?year&month`, `loadRecentApprovals`) | **ingesting** — supersedes the yearly PDF lists |
| CDSCO Rule 84AB brand registry (`CDSCO/brandNames`) | Every registered brand name → licensed manufacturer, licence number, generic | live | JSON search (`loadRule84abBrandNames?searchText`), enumerable by 2-letter prefixes | **ingesting** |
| CDSCO alerts, gazette, FDC bans, SEC, approvals PDFs | see METHODOLOGY | daily | HTML/PDF | ingesting (existing) |
| NPPA compendium, orders, Authority minutes | ceiling prices, notifications | weekly | encrypted JSON / HTML | ingesting (existing) |
| PMBI Jan Aushadhi | generic MRPs | weekly | JSON | ingesting (existing) |
| NLEM 2022 | essential medicines | static | PDF | ingested |
| CDCI — Common Drug Codes for India (NRCeS / C-DAC) | National drug terminology: brands, generics, substances (CAS, UNII, SMILES, InChI), suppliers, dose forms | release 2026-06 (notes 2026-08) | official files need NRCeS registration; 2026-07 copy on GitHub (`dhananjaydpatkar/cdci_graph`) | **ingesting (mirror copy)** — register at nrces.in for the official feed |
| IPC / PvPI | drug safety alerts, ADR signals, publications | irregular | HTML/PDF | planned |
| Department of Pharmaceuticals | schemes (PLI, bulk-drug parks), annual reports | quarterly | HTML/PDF | planned |
| RMSCL Rajasthan rate contracts (`DrugsRC.html`) | ~2,000 active contracts: item, supplier, unit, rate, GST, L1/L2, contract validity | per tender, rechecked Tue/Fri | HTML table | **ingesting** (`rmscl_rates`) |
| TNMSC Tamil Nadu tenders (`drugtender.php?drugcat=…`) | L1 rate per pack for essential, speciality, veterinary drugs, surgicals and sutures, every matched supplier with order share; current and previous tenders | per tender, rechecked Wed/Sat | HTML (nested tables) | **ingesting** (`tnmsc_rates`) |
| Kerala KMSCL, other state corporations | procurement prices | per tender | portals redirect / PDF | candidate |
| PIB press releases | government announcements | daily | RSS (all ministries, Hindi by default) | not added — Google News feeds already surface the pharma-relevant releases |
| ONDLS (state drug licences) | manufacturing/sale licences | live | unreachable (DNS) | blocked |
| CTRI | Indian trial registry | live | CAPTCHA | not scraped (via ClinicalTrials.gov) |

## Tier 2 — markets and corporate

| Source | What it holds | Access | Status |
|---|---|---|---|
| NSE corporate announcements | filings per listed group: results, USFDA observations, M&A, plant actions | JSON (session cookie) | **ingesting** |
| NSE/Yahoo quotes | prices, history, fundamentals | API | ingesting (existing) |
| BSE announcements | same as NSE | API blocks non-browser clients | blocked |

## Tier 3 — international regulators (Indian manufacturers abroad)

| Source | What it holds | Access | Status |
|---|---|---|---|
| openFDA bulk: drugsfda (29k), Orange Book (49k), NDC (138k), enforcement (18k), shortages (1.6k), labels (263k) | US approvals and ANDAs held by Indian firms, patents and exclusivity (generic-entry dates), US labels for molecule depth | bulk zip | **ingesting** (labels: molecule-level subset) |
| FDA Import Alert 66-40 | ~470 firms under cGMP import refusal (110 in India), with address and date listed | HTML | **ingesting** (`fda_ia_6640`) → `usfda_actions`, events for new Indian firms |
| WHO prequalified medicines | 656 products, applicants | CSV | **ingesting** |
| WHO medical product alerts | 83 falsified/substandard alerts (latest N°3/2026, Jul 2026) | HTML | **ingesting** (`who_alerts`) → `reg_documents`, events for the last 12 months |
| EMA medicines register | EU authorisations incl. Indian generics | XLSX | **ingesting** |

## Tier 4 — molecule science

| Source | Holds | Access | Status |
|---|---|---|---|
| WHO ATC/DDD index | DDD values (ATC codes now come from ChEMBL) | HTML per code | candidate |
| ChEMBL | ATC codes, mechanism of action, max phase, first approval, boxed-warning / withdrawn flags, indications with phase | REST | **ingesting** (`molecule_enrichment`) |
| openFDA label API | latest single-ingredient US prescribing label: boxed warning, indications, contraindications, warnings, ADRs, interactions, mechanism, pregnancy, overdose | REST (1k req/day without key; set `OPENFDA_API_KEY` for 120k) | **ingesting** (`molecule_enrichment`) |
| openFDA FAERS | top reported adverse reactions per molecule (spontaneous reports — signal, not incidence) | REST count queries | **ingesting** (`molecule_enrichment`) |
| PubChem | identifiers, properties | REST | planned |
| RxNav (NLM) | normalised names, RxCUI | REST | planned |
| DDInter, SIDER | drug–drug interactions, side effects | download | planned |

## Tier 5 — compiled datasets (secondary; provenance labelled)

| Source | Notes | Status |
|---|---|---|
| Indian Medicine Master Dataset (Kaggle, Sept 2026) | catalog spine, 17 merged sets | ingested |
| 1mg 2025 scrape (Kaggle) | 2025 MRPs, stock | ingested |
| junioralive/Indian-Medicine-Dataset (GitHub, updated 2026-06, MIT) | 254k brands; diffed 2026-10-17: all 248,736 distinct names already in the master dataset — copy kept in `data/sources/junioralive/` | checked, nothing new |
| medcheck, nuskha, Nazar (GitHub) | derived NSQ / WHO-alert sets; used to locate official endpoints | reference only |
| DrugSetu API | live MRP + safety; trial quota exhausted | cached copy kept |

## Not used
Live scraping of e-pharmacy sites (1mg, PharmEasy, Netmeds, Apollo): their terms restrict automated collection.
