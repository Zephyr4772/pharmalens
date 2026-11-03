# US FDA inspections → plants (2026-11-03)

## What was added
- **Feed `fda_inspections`** (weekly, Tue 06:40) pulls every drug inspection and Form 483 citation from the FDA Data
  Dashboard API, using the `FDA_DD_USER` / `FDA_DD_KEY` already in the server's .env. The first live run took 30 s and
  loaded 39,661 drug inspections (2,987 in India) and 38,178 citations. Licence: `fda_web` (US government, open).
- **Sites linker** now places inspections on plants. Methods, each stored with its confidence and evidence in
  `entity_links` (linker `site:records`):
  - `locality_match` 0.85: the maker's single PIN-keyed site that shares the address's place words.
  - `district_site` 0.85: maker + state + district. FDA gives Indian firms a city but no state or PIN, so the state
    comes from our other Indian addresses for that city, used only when at least 90% of them agree.
  - `address_postal` 0.9: abroad only. It joins a site that an Indian import approval already lists, and never
    creates one.
  - `same_fei` 0.95: another inspection with the same FEI (FDA's establishment ID) is placed, and all such
    placements agree.
  - The FEIs seen at each site are recorded in `sites.fei`.
- **What is not placed:**
  - Clinical investigators, hospitals and CROs (Bioresearch Monitoring), unless the firm is a known maker.
  - Plants abroad that no India-facing source lists.
  - Numbers in FDA street addresses. These are survey or plot numbers and are never read as a PIN.
- **UI (already built):** site pages show a US FDA inspections panel (classification, project, FEI and 483 counts)
  and a summary tile. Maker sites and group plants show the last inspection and the OAI count.

## Coverage (audit.py, server copy)
| measure | before | after |
|---|---|---|
| US FDA inspection (India) → site | 0 | 72.5% (2,166 / 2,987); about 93% of the 2,333 that aren't Bioresearch Monitoring |
| sites with a US FDA inspection | 0 | 699 / 4,705 (14.9%) |
| curated-group sites with a US FDA inspection | 0 | 175 / 527 (33.2%) |
| sites | 4,363 | 4,705 (Indian plants first seen in an inspection) |

## Precision
50 random links in `docs/link-samples/fda-inspections.md`: all 50 have the right firm and place. Earlier draws caught
four faults, all fixed before the final draw:
- clinical investigators made into sites;
- survey numbers read as PINs;
- US parents joined to Indian namesakes (Merck & Co → Merck Ltd);
- 13,000 sites created for foreign firms with no Indian link.

**Known limit:** a district site is district-level. A maker with several units in one district (for example Hetero
in Hyderabad) shares one district site until a PIN-keyed source places each unit.

## Events
New OAI inspections of Indian firms raise a high-severity `usfda` event. The first load was the baseline, so no
events were raised for history.

## Warning letters and import refusals (same day)
- **Feed `fda_compliance`** (weekly, Tue 06:55) uses the same key. It loads:
  - every drug compliance action: 2,839, of which 210 are Indian. Indian ones are 223 warning letters plus 2
    injunctions in the raw pull.
  - every refused drug shipment from India: 11,643.
  - Licence: `fda_web`. New warning letters and injunctions against Indian firms raise high `usfda` events (none for
    history). Refusals raise no events.
- **Placement:**
  - FEI first, then firm + place.
  - Warning letters and refusals only join sites that other records define, so a shipper's office never becomes a
    "plant".
  - Outside the FEI rule, they're kept only for known makers or FEIs that have been inspected, which keeps out web
    shops and clinics.
- **Coverage:**
  - Indian warning letters and injunctions placed on a plant: 79.5% (167 / 210).
  - Refused shipments placed: 27% (3,138 / 11,643). The rest are shipped from offices, traders or exporters with no
    plant record.
- **UI:**
  - Site pages have a "US FDA warning letters and import refusals" panel.
  - Plant lists show WL and IR badges.
  - The group dossier's US FDA scorecard row adds the plants' record: OAI inspections, warning letters (2 years) and
    refused shipments (12 months). OAI or a warning letter turns it red; 10 or more refusals in 12 months turns it
    amber.
- **Fixes made along the way, which apply to all sources:**
  - A PIN must fit a state the address names. Door and survey numbers had been read as PINs; 45 sites were
    re-keyed.
  - The firm's own name in a street no longer counts as a shared place word.
  - "Distt" is treated as a generic word.
  - FEI joins need the record's place to agree with the site.
- **Sample:** 50 random links in `docs/link-samples/fda-compliance.md`, all 50 correct.

## Known issues
- **Coarse district labels:** a few district sites take the last word of a place name (`telangana:hills` for
  Banjara Hills, `himachal pradesh:sahib` for Paonta Sahib). The firm and area are right; only the label is
  coarse.
- **FDA's own inconsistencies:** some records give a street in one city and the city field in another (USV
  "Peenya" street with "Govandi" city). The street wins.
- **Memory:** the entity linker ran out of DuckDB memory (600 MB cap) twice after a feed ran in the same process. A
  container restart fixed it, and the deploys since have each started fresh. Watch the 05:10 linker on Wednesday,
  after Tuesday's FDA feeds.
- **Screener flags:** these still use import alerts and recalls only. The plant record shows on the dossier
  scorecard, not yet in the screener's per-row flags.
