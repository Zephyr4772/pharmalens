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

## Next
FDA warning letters and import refusals from the same Data Dashboard key, matched to makers and sites.
