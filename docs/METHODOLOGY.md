# Methodology

## Sources and refresh cadence

| Feed | Source | Cadence | Notes |
|---|---|---|---|
| Catalog | Indian Medicine Master Dataset (Kaggle, Sept 2026; 17 merged sets from 1mg, Apollo, Netmeds, NPPA) | rebuild on demand | 543k products, joined on normalised name |
| 2025 prices | 1mg scrape (Kaggle `apkaayush`, 2025) | static | Newer MRP, Rx flag, in-stock flag for ~251k products |
| DrugSetu | api.drugsetu.com | every 6 h + on product view | Live MRP per pack, safety profile; newest-first list = launch feed. Trial: 5 items/page, ~1 req/s, capped quota |
| CDSCO NSQ / spurious | cdsco.gov.in NSQ archive | daily 09:10 | Monthly central + state lab PDFs, parsed to batch level |
| NSQ mirror | thehealthmaster.com | daily 09:40 | CDSCO moved NSQ to a new portal in Aug 2025; later months come from republished CDSCO PDFs, labelled "via mirror" |
| Prohibited FDCs | cdsco.gov.in Drugs › FDC | daily 09:00 | Every Section 26A notification since 1983 (690 entries) |
| Gazette | CDSCO gazette notifications | daily 08:50 | Prohibitions, rule amendments, drafts |
| Alerts / circulars / notices | CDSCO | 08:05, 14:05, 20:05 | Recalls, theft, falsified products |
| NPPA | nppa.gov.in | 10:15, 17:15 | Orders, draft price-calculation sheets, Authority minutes, overcharging |
| Jan Aushadhi | janaushadhi.gov.in API | Mon/Thu | All PMBI generics with MRP; additions and MRP changes become events |
| NSE | Yahoo Finance | every 5 min in market hours, fundamentals 18:30 | ~15 min delayed |
| openFDA | api.fda.gov enforcement | daily 07:20 | Recalls where the recalling firm is in India |
| News | ET HealthWorld, Express Pharma, targeted Google News queries | every 15 min | Topic-classified, tagged to groups/molecules |
| CDSCO new drug approvals | CDSCO Approved New Drugs yearly lists | daily 09:25 | Drug, indication, approval date since 2015 (current-year list re-read every run) |
| SEC recommendations | CDSCO Subject Expert Committees | 11:45, 18:45 | Every agenda item parsed: file no., drug, firm, committee, division (trial / marketing / BE / biological) and outcome (recommended / more data / not recommended) |
| NLEM 2022 | nppa.gov.in | monthly | 384 essential medicines with care level and forms; sets the NLEM flag on molecules |
| Clinical trials | ClinicalTrials.gov API v2 (Indian sites) | daily 05:40 | Interventional trials updated in the last 3 years. CTRI's own search is behind a CAPTCHA, so CTRI ids come from cross-registration |
| NPPA compendium | NPPA IPDMS dashboard | weekly (Tue) | All current ceiling prices (S.O. of 25-Mar-2026) plus company-specific special-feature prices. The dashboard's request encryption (AES + RSA-wrapped key, CSRF token) is reproduced exactly as the public page does it; revisions become events |

Every connector run is recorded in `connector_runs`, and new rows become `events` that stream to the UI over SSE.

## Catalog normalisation

- **Molecules** come from the master dataset's medicine→molecule links. Salt-form suffixes (hydrochloride, sodium, trihydrate…) and Indian/INN spelling variants are folded into one key.
- **Combinations** are the unit of substitutability: the same molecules, the same strengths and the same dosage-form family (tablet, capsule, injection, oral liquid, topical, eye/ear drops, inhalation, powder, suppository). Price bands are per unit; units below 15% or above 20× of the median are excluded as pack-parsing outliers.
- **Companies** are deduplicated on legal-suffix-free names. **Groups** (`seed/parents.json`) roll up subsidiaries and acquired brand houses, for example Sun = Sun Pharma + Sun Pharma Labs + Ranbaxy, and Torrent includes Elder's brands. Patterns are anchored on word boundaries.

## Market share (estimate)

No free sales data exists for India; AIOCD-AWACS and IQVIA are paid. Each active SKU gets a weight:

    weight = sqrt(MRP per pack) × availability × reach
    availability = 1.0 in stock (2025 scrape) · 0.6 unknown · 0.25 out of stock · 0 discontinued
    reach        = 1 + ln(1 + number of independent catalogues listing the SKU)

- **Value share** is an owner's weight divided by the segment total. **SKU share** is the plain count share.
- Segments are therapy class, molecule and combination. Owners are groups where mapped, otherwise companies.
- **HHI** is computed on value shares: above 2,500 is concentrated, below 1,500 is fragmented.

The square root dampens price. Pure MRP weighting let a few lakh-rupee oncology biologics put Roche ahead of every Indian major. With the square root, the top of the ranking (Intas, Sun, Zydus, Cipla, Lupin, Torrent, Alkem…) closely tracks published IPM rankings. Absolute percentages are understated, because thousands of small marketers list many low-volume SKUs. Read ranks and relative positions, not exact percentages.

## Ban matching

A product is flagged **banned** only when all of these hold:
1. Its molecule set equals the notification's molecule set.
2. Every strength stated in the notification matches the product's strength.
3. Every dosage-form qualifier in the notification ("suspension", "dispersible", "SR", "injection"…) appears in the product's form, name or pack.

It is marked **check pack** (review) instead when the product lacks the strength detail, or when the notification lists the same ingredient twice so that the molecule set alone cannot confirm it.

Court stays won by individual manufacturers are **not** tracked. Always confirm against the linked notification.

## NSQ matching

- Manufacturer text is resolved to catalog companies by a normalised-prefix match.
- Molecules are extracted from the product text by longest n-gram match.
- The SHELF check matches exact batch numbers, and requires the product name to be similar or the same marketer.
- Some older CDSCO PDFs (mostly 2022–2023 revised lists) are scanned images and parse to 0 rows. They are listed in the feed note and would need OCR.

## Known limitations

- Catalog MRPs are dated, and the "as of" year is shown everywhere. DrugSetu live prices refresh individual products when they are viewed.
- SEC outcomes are classified from the recommendation wording; ambiguous text is marked "noted". Read the linked PDF for the full recommendation.
- The US FDA shortage list is a 2024 snapshot and is labelled as US data.

## Alerts

A subscription combines what to watch with where to send it:
- **Watchlist**: starred groups, companies, molecules, combinations or SKUs. An event matches when it is about one of them (entity, molecule ids, ban molecule set, or the name appearing in the headline). New NSQ batches for watched makers or molecules are matched directly, even when they raise no tape event.
- **Shelf list**: an inventory CSV re-checked with the SHELF engine whenever new bans, NSQ/spurious lists, recalls or price notices arrive. Only flags that were not present on the previous check are sent, so you hear about each problem once.
- **Filters**: event kinds and a minimum severity. With no watchlist and no shelf list, every event that passes the filters is sent.
- **Delivery**: instant and/or a daily digest at a chosen IST hour. Channels are Telegram (bot), email (SMTP) and HTTPS webhooks (Slack, Discord, Teams or any JSON receiver). Every alert is also kept in the in-app inbox with per-channel delivery status.

The dispatcher runs every 2 minutes and immediately after any feed lands new events. At most 25 instant alerts are sent per subscription per run; the remainder are summarised with a link to the inbox. Channel credentials go in `.env` (see `.env.example`).
