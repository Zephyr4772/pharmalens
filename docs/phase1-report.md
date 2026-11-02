# Phase 1 report: links for depth and unison

Built 2026-11-02/03 against `docs/data-depth-audit.md`. All seven items shipped, none skipped. Each is its own
commit, so any one can be reverted alone; every new link lives in new tables (`entity_links`, `event_entities`,
`price_unit_obs`, `launch_signals`, `auto_groups`, `linker_runs`) or a new column (`parents.group_kind`). No
existing column, row or screen was changed or hidden, and nothing public-facing was added.

| # | Item | Commit |
|---|---|---|
| 4 | Molecule resolver over brand registry, brand first-seen, US FDA recalls, trials, news, tenders | `5d6fff7` |
| 6 | US & EU status (Orange Book, patents/exclusivities, EMA) on product and molecule pages | `5f762ea` |
| 9 | Multi-entity events + timelines on molecule, product, combination, company, group pages | `30cb0ae` |
| 11 | Pack-aware unit prices | `54d9911` (+ `df9582a`: same logic as one SQL statement for the 2 GB server) |
| 12 | Banned FDC → combination matcher | `290db37` |
| 5 | Launch dating (`launch_signals`) + new-brand → company links | `dc12c2a` |
| 3 | Company resolver, auto-groups (`group_kind` curated/auto), approval → company | `1cacd7c` |

How the numbers were made: `analysis/audit.py` (re-runnable on any copy of the database) was run on a snapshot of
the live database before any change (`analysis/runs/baseline.json`) and after each item on a working copy of the same
snapshot (`analysis/runs/after_<item>.json`); the final live numbers come from the server after the linker ran
(`analysis/runs/live_after.json`). "Linked" counts the table's own column or a high-confidence link (≥ 0.85);
inferred links are counted separately and never as coverage. Spot-check samples (50 links each, with evidence) are
in `docs/link-samples/`.

## Rules applied

- **Precision over recall.** Molecule resolution is an exact dictionary match (no fuzzy matching anywhere). Every
  link stores method, confidence, evidence and a licence tag. The UI shows links ≥ 0.85; lower ones appear only
  behind a "show inferred" tick and carry an INFERRED badge, with the evidence on hover.
- **Quality and regulatory records are never attached on a weak match.** US FDA recalls are resolved only from
  their structured product description (class prefix, NDC, manufacturer text stripped), never from prose. NSQ /
  SEC / approval / debarment events link to molecules only from the structured product part of the headline;
  connector-supplied molecule ids that the headline does not confirm drop to inferred (they included excipients:
  "Fitusiran → dibasic calcium phosphate"). A record reaches an ingredient combination only on a *complete*
  resolution of its whole ingredient list. Partial ban matches (which the sample shows are usually a different,
  smaller combination) stay inferred.
- **Confidence vs completeness.** Confidence answers "does this record involve this molecule"; the method
  (`dict_complete` / `dict_partial`) says whether the record's whole ingredient set is known. Set comparisons
  (P2, P5, ingredient-set links, bans) use complete records only.

## Coverage before → after

| Item | Measure | Before | After |
|---|---|---:|---:|
| #4 | brand registry → molecule | 0.0% | 90.1% |
| #4 | brand first-seen → molecule | 0.0% | 94.8% |
| #4 | US FDA recall → molecule | 0.0% | 94.4% |
| #4 | tender → molecule | 65.6% | 69.9% |
| #4 | trial → molecule | 39.8% | 39.9% |
| #4 | news → molecule | 10.0% | 10.0% (1,865 new high links all on articles already tagged; 3,988 articles gained inferred links only) |
| #6 | active product → US Orange Book (same ingredient set) | 0.0% | 39.6% |
| #6 | active product → live US patent / exclusivity | 0.0% | 20.0% |
| #6 | active product → EMA authorisation | 0.0% | 11.0% |
| #6 | molecule → single-ingredient US record | 0.0% | 19.6% |
| #9 | event → any entity | 52.4% | 66.6% |
| #9 | event → 2+ entities | 0.0% | 25.0% |
| #9 | event → molecule | 1.3% | 32.7% |
| #9 | event → ingredient set (complete only) | 0.0% | 10.7% |
| #9 | event → group | 39.9% | 49.7% |
| #11 | products with 2+ price points that have a comparable per-unit series | 0.0% | 60.2% |
| #11 | …of which still jump ≥ 1.8× (raw history: 8.0%) | — | 0.5% |
| #12 | banned FDC → combination | 29.9% | 31.7% (the ceiling: see below) |
| #5 | brand first-seen → company | 0.0% | 84.9% |
| #5 | molecule → dated India launch signal (high) | 0.0% | 9.1% (16.9% incl. inferred CDCI dates) |
| #3 | company → group (curated or auto) | 1.0% | 100.0% (8.2% in multi-name auto-groups) |
| #3 | active product → group (curated or auto) | 14.4% | 82.1% (= every SKU with a company) |
| #3 | CDSCO approval → company | 0.0% | 72.1% |

Notes on the smaller moves:
- **#12** is at its ceiling. Of 690 bans, 420 name a specific multi-ingredient set that resolves completely; 211 of
  those sets are actually marketed and all 211 are linked (the other 209 are simply not sold). 241 are class-level
  wordings ("FDCs of vitamins with anti-inflammatory agents") that name no specific set; 74 are single-ingredient
  bans, now linked to the molecule.
- **Trials and news** barely move because the existing columns already held what an exact match can find; the new
  links add per-intervention resolution and labelled evidence, and news keeps 3,988 inferred-only mentions out of
  the default view.

## The five test paths (end to end, every hop at once)

| Path | Before | After | What moved |
|---|---:|---:|---|
| P1 NSQ batch → product → molecule → maker → group → ticker → price → news (since 2025, n = 4,770) | 1.0% | 1.0% | maker → group (any) 220 → 2,425 via auto-groups, but tickers exist only for curated groups; the product hop (no SKU link) is unchanged |
| P2 SEC → molecule → approval → brand registration → NPPA price → dated first listing (since 2024, n = 4,531) | 0.0% | 2.5% | brand registration hop 0 → 892, dated first listing 0 → 462 |
| P3 US FDA action → plant → company → group → ticker → US apps (Indian, n = 272) | 0.0% | 0.0% | molecule hop 0 → 151 (recalls); the plant hop does not exist yet (Phase 2) |
| P4 Tender → molecule → product → maker → quality record (n = 7,453) | 12.1% | 12.2% | molecule hop 4,890 → 5,211; supplier → company is unchanged (suppliers were already resolved at ingest wherever an exact firm key exists) |
| P5 Patent → molecule → US generics → India products → dated India launch (molecules with live US patents, n = 518) | 0.0% | 30.7% | dated India launch 0 → 174 (NPPA launch prices and registry arrivals) |

## Skipped

Nothing. Two items changed shape for technical reasons, both noted in their commits:
- **#6** first linked every combination to every matching Orange Book product (540k rows, too heavy for the 2 GB
  server). It now goes through an ingredient-set node (combination → set, US/EU record → set: ~82k rows) with the
  same precision.
- **#11** first ran in Python (~1 GB peak) and was rewritten as one DuckDB statement; same result.
- **#3**: the curated group patterns already cover every company they can (zero new curated hits among 15,522
  unlinked companies), so #3 became name-variant auto-groups + singletons rather than lifting curated coverage.

## False-link risks noticed

1. **Messy molecule nodes.** The catalog's molecule list contains junk and duplicates (1,959 molecules occur in a
   single product). Links can land on a node like "Clotrimazole Topical" or "Minerals" rather than the clean
   molecule; salt-word nodes ("Chloride", "Sodium") are now skipped. Duplicates ("Amoxycillin" / "Amoxicillin",
   "Clavulanic Acid" / "Potassium Clavulanate") also cost recall in every exact-set match (e.g. Clavam's US status).
   Molecule hygiene is the next foundation fix.
2. **US status is per ingredient set, any form.** A paracetamol tablet shows the live patents of IV paracetamol
   (Ofirmev). The panel says "any strength or form"; a form-aware match would be stricter.
3. **News "drug" mentions** (0.85) are distinctive drug names with an ATC code in a headline; a headline listing 30
   drugs ("NPPA fixes prices of 30 drugs including …") links to each named one.
4. **Auto-group name variants** (0.85): two genuinely different small firms can share a name ("Sunrise Pharma" in
   two states). Without CIN / address data this cannot be told apart.
5. **CDCI record dates** are "added or last updated" dates, so they are inferred (0.7) and excluded from the path
   counts.
6. **Data issue (not a link error):** the 2025 "MRPs" from the 1mg scrape sit almost exactly 6.25% below the
   2022-24 MRP on identical packs, which suggests that scrape recorded a discounted selling price. Per-unit trends
   between those two sources overstate price cuts.
7. **Licence of links is mostly "internal"** even when the record is open (US FDA, Gazette), because the molecule,
   combination and company nodes come from the non-commercial catalog. Each link's `licence` column records this.

## Sources used and their licence tags

Licence classes from `backend/pharmalens/licensing.py` (strictest source wins). Every link row also carries its own
`licence` (strictest of the record and the node it points to). New derived tables are registered there too.

| Table / file | Used by | Sources | Licence class |
|---|---|---|---|
| brand_registry | #4, #2-path | CDSCO website | permission |
| brand_first_seen | #4, #5 | CDSCO + CDCI + ours | permission |
| reg_approvals | #3 | CDSCO website | permission |
| procurement_rates | #4 | state corporations | permission |
| jan_aushadhi | #9 | PMBI | permission |
| reg_banned_fdc | #12 | Gazette of India | gazette |
| nppa_retail_prices | #5 | Gazette of India | gazette |
| usfda_actions | #4, #9 | openFDA / FDA web | open |
| us_orange_book, us_patents | #6 | openFDA | open |
| ema_medicines | #6 | EMA | attribution |
| trials | #4, #9 | ClinicalTrials.gov | attribution |
| cdci_brand / cdci_generic / cdci_substance | #5 | CDCI (CC BY 4.0, India) | attribution |
| mfr_prices | #11 | manufacturers' Form V lists | attribution |
| news | #4, #9 | publishers / GDELT | internal |
| corp_announcements, quote_history | #9, paths | NSE | internal |
| events | #9 | mixed feeds | internal |
| molecules, combos, product_molecules, companies, products, price_observations | all (nodes) | Kaggle catalog (non-commercial) + ours | internal |
| data/derived/price_packs.parquet | #11 | Kaggle catalog sources | internal |
| parents (curated groups) | #3, #9 | ours | open |
| entity_links, event_entities, price_unit_obs, launch_signals | new | mixed: per-row `licence` column | per row |
| auto_groups | #3 | catalog company names + ours | internal |
| linker_runs | new | ours | open |

## Operations

- `entity_linker` runs daily at 05:10 (after the morning feeds) and re-derives every link; each linker replaces only
  its own rows (`DELETE … WHERE linker = …` reverts one).
- Run by hand: `py -3 -m pharmalens.linking [molecules global_status events prices bans launches companies]`.
- Audit: `py -3 analysis/audit.py <db> [--json out.json]` (`AUDIT_MEMORY=400MB` on the server).
- Samples: `py -3 analysis/samples.py <db> <item> <linker-prefix|event_entities|price_unit_obs> [n]`.
- `data/derived/price_packs.parquet` is built locally (`py -3 -m pharmalens.pipeline.price_packs`, where the raw
  catalogs live) and copied to the server's `data/derived/`; without it, every catalog price point falls back to
  "pack assumed" and nothing is marked comparable.

## Recommendation: what to build next

1. **Molecule hygiene** (merge duplicate and brand-glued molecule nodes, with a reviewed alias table). It is now the
   main limit on every exact-set match built here (US status, bans, timelines, launch sets) and on recall in #4.
   Small effort, multiplies Phase 1.
2. **Maker / plant, stage 1 (maker entity)** from `products.manufacturer_raw`, NSQ manufacturer, approval
   applicant/sites and US FDA firm names, resolved with the same exact firm key used in #3. This is the only way
   P1 and P3 move: both are blocked at product → maker and action → plant.
3. **NSQ → product resolver** (maker + exact ingredient set + strength + form), now feasible because ingredient
   sets and auto-groups exist; it unlocks product-level quality records and lifts P1's first hop.
4. **Record pages** for NSQ batch, SEC item, approval, trial, tender and patent, reading `entity_links` and
   `event_entities` both ways: the remaining step for "any fact reachable from any other".
