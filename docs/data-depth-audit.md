# Data depth and unison audit

Measured 2026-11-02 on a snapshot of the live server database (read-only copy, audit script in the session
scratch). Analysis only: nothing in the code or data was changed.

**Definitions used throughout**
- **Depth**: an entity's profile shows everything we hold about it.
- **Unison**: every record links to every related record, so any fact is reachable from any other.
- **Coverage %**: the share of rows in the source table that carry a resolved link to the neighbouring entity.
  "Active" products exclude discontinued and the 23 remaining placeholder ("lorem") rows: 535,507 of 543,274.

## Summary

We hold a lot, but much of it is not connected.

- **The product ↔ molecule ↔ combination spine is strong** at 89.5%, and so is the group-level market data
  (100%). The edges that carry quality, regulatory and launch facts are weak.
- **Three resolution gaps account for most of the broken paths.**
  1. **Who made it.** There is no manufacturer or plant entity, although we hold 17,262 distinct "manufactured
     by" strings on products, NSQ manufacturers, CDSCO approval site addresses and US FDA firm names.
  2. **Who is it.** Company → group covers 1% of companies and 14% of active SKUs. Approvals → company is 3%;
     brand first-seen → company is ~0%.
  3. **What is it.** Generic-name text in the brand registry, new-brand tracking and US FDA actions is never
     resolved to molecules.
- **Only five entity types have a profile page.** Product, molecule, combination, legal company and group do.
  NSQ batch, SEC item, approval, trial, tender, patent, US application, news item and plant have none, so a fact
  stored on one of those can only be seen as a row inside someone else's page.
- **None of the five test paths runs end to end for more than ~2% of starting records.**

## 1. Entity inventory

Stable-ID column key:
- **registry**: a permanent id in `id_registry` that survives rebuilds.
- **natural**: the source's own key (NCT number, application number, NSE seq id).
- **seq + dedupe**: a database sequence that is stable while the table is never truncated, with a unique
  `dedupe_key` behind it.

| Entity | Table | Rows | Stable ID | Own page | Key neighbour links (coverage) |
|---|---|---:|---|---|---|
| Product / SKU | products | 543,274 (535,507 active) | registry | yes `/p/:id` | company 82.1%, molecule 89.5%, combo 89.5%, group 14.4%, MRP 73.5%, pack qty 63.9%, label text 28.1%, maker string 82.1% (unresolved) |
| Molecule | molecules | 5,006 (1,959 in one product only) | registry | yes `/m/:id` | ATC 50.8%, ChEMBL 32.1%, CDCI substance 29.4%, therapy class 39.7% |
| Combination (FDC) | combos | 40,185 | registry | yes `/c/:id` | molecules 100% (derived), banned list 29.9% of bans resolve to a combo |
| Legal company (marketer) | companies | 15,680 | registry | yes `/co/:slug` | group 1.0% (158 companies) |
| Corporate group | parents | 86 (48 listed) | slug (curated) | yes `/g/:slug` | ticker 48/48, quotes 48, results 46 |
| Manufacturer / plant / site | none | 0 | none | no | exists only as text: `products.manufacturer_raw` (17,262 strings), `reg_nsq.manufacturer`, `reg_approvals.sites` (92% of approvals), `usfda_actions.firm`, `cdci_supplier` (8,121) |
| NSQ / spurious batch | reg_nsq | 10,019 | seq + dedupe | no | company 51.5%, molecule 90.4%, group 5.3%, product 0% (14% resolvable) |
| Banned FDC | reg_banned_fdc | 690 | seq + dedupe | no | combo 29.9% |
| SEC item | sec_items | 14,023 | seq + dedupe | no | molecule 69.0%, company 56.1%, group 49.4% |
| CDSCO approval | reg_approvals | 4,027 | seq + dedupe | no | molecule 88.8%, company 3.3% (applicant text 92%), sites text 92% |
| Brand registration (CDSCO 84AB) | brand_registry | 90,464 | none (firm + licence + brand) | no | company 72.7%, molecule 0% (generic text 95%), product 9.4% |
| CDCI brand / supplier | cdci_brand, cdci_supplier | 93,019 / 8,121 | natural (CDCI ids) | no | molecule 67.5% (via generic → substance), company 0% |
| New-brand first sighting | brand_first_seen | 183,483 (39 post-baseline) | natural | no | company ~0% (37 rows), molecule 0% |
| NPPA ceiling price | nppa_ceiling (+history 1,845) | 937 | natural | no | molecule 89.0% |
| NPPA retail (launch) price | nppa_retail_prices | 3,550 | natural | no | molecule 98.2%, company 73.1%, product 0% |
| Manufacturer price list line | mfr_prices | 18,024 | natural | no | product 44.5%, group 96.2% |
| Jan Aushadhi item | jan_aushadhi | 2,445 | natural (drug code) | no | molecule 87.5% |
| NLEM entry | nlem | 484 | none | no | molecule 93.8% |
| Tender / rate contract | procurement_rates | 7,453 (TNMSC, RMSCL, HMSCL) | none | no | molecule 65.6%, company 42.5%, product 14.1% |
| Debarment | firm_debarments | 42 | dedupe | no | company 31.0%, molecule 88.1% |
| PvPI safety alert | pvpi_alerts | 193 | dedupe | no | molecule 96.4% |
| Shortage (US) | shortages | 1,588 | seq | no | molecule 84.1% |
| US FDA action | usfda_actions | 630 (272 India) | id | no | group 7.8% (18% of Indian), molecule 0%, plant 0% |
| US application | us_applications | 29,424 | natural | no | molecule 87.7%, group 23.8% |
| Orange Book product | us_orange_book | 48,865 | natural | no | molecule 90.2%, group 29.4%; **never surfaced** |
| US patent / exclusivity | us_patents | 19,963 | natural | no | molecule 66.8% (605 molecule sets) |
| US NDC listing | us_ndc | 138,173 | natural | no | molecule 81.4%, group 12.1% |
| WHO-PQ product | who_pq | 658 | natural | no | molecule 95.6%, group 64.0% |
| EMA medicine | ema_medicines | 2,754 | natural | no | molecule 66.5%, group 27.5% |
| Clinical trial | trials | 2,012 | natural (NCT) | no | molecule 39.8%, group 29.4%, CTRI id 1.9% |
| Listed security | quotes / quote_history | 51 / 244,857 | ticker | via group | group 100% |
| Quarterly result | fin_results | 944 | natural | via group | group 100% |
| Board meeting | results_calendar | 880 | natural | via group | group 100% |
| Exchange filing | corp_announcements | 41,063 | natural (NSE seq) | no | group 100%, molecule 0%, plant 0% |
| News item | news | 60,223 | seq | no | group 18.9%, molecule 10.0%, product 0% |
| Regulator document | reg_documents | 4,146 | seq + dedupe | no | none |
| Event (derived) | events | 2,415 | seq + dedupe | no | entity 52.1% (one entity per event at most) |
| Price observation | price_observations | 657,211 | product + date | via product | 8% of products with 2+ points jump ≥1.8× (pack mixing) |
| Should hold, don't | — | — | — | — | patents (India), plants, key people, shareholding, DMFs/CEPs, exports, court cases, more state tenders: see §4 |

## 2. Link matrix

Resolution methods:
- **id**: a foreign key set at ingest from a structured source id.
- **name**: normalised-name match or alias lookup.
- **text→mol**: our molecule resolver run over free text.
- **derived**: computed from other links.
- **none**: no link exists.

Rows are the record; columns are the entity it should reach.

| ↓ record / reaches → | Product | Molecule | Combo | Company | Group | Plant | Ticker |
|---|---|---|---|---|---|---|---|
| Product | — | 89.5 id | 89.5 derived | 82.1 name | 14.4 derived | **none** (text 82%) | via group |
| NSQ batch | **0 none** (14% resolvable) | 90.4 text→mol | **none** | 51.5 name (maker) | 5.3 derived | **none** | 1.9 |
| Banned FDC | via combo | id | 29.9 key | — | — | — | — |
| SEC item | **none** | 69.0 text→mol | **none** | 56.1 name | 49.4 name | **none** | via group |
| Approval | **none** | 88.8 text→mol | **none** | **3.3** name | **none** | **none** (sites text 92%) | — |
| Brand registry | 9.4 name | **0** (text 95%) | **none** | 72.7 name | derived | — | — |
| CDCI brand | **none** | 67.5 id chain | **none** | **0** (supplier id 100%) | — | — | — |
| Brand first-seen | **none** | **0** | **none** | **~0** | — | — | — |
| NPPA retail price | **none** | 98.2 text→mol | **none** | 73.1 name | derived | — | — |
| Mfr price list | 44.5 name+strength | via product | via product | name | 96.2 name | — | — |
| Tender rate | 14.1 derived | 65.6 text→mol | **none** | 42.5 name | derived | — | — |
| US FDA action | — | **0** | — | **none** | 7.8 name | **none** (no FEI) | 6.0 |
| US application / OB / NDC | — | 88 / 90 / 81 text→mol | — | — | 24 / 29 / 12 name | **none** | via group |
| Trial | — | 39.8 text→mol | **none** | **none** | 29.4 name (industry only) | — | — |
| Exchange filing | — | **none** | — | — | 100 id | **none** (plant topic exists) | 100 |
| News | **none** | 10.0 text | — | **none** | 18.9 name | — | via group |
| Event | per kind: 52.1% have one entity, never more than one |  |  |  |  |  |  |

**Blocking edges** (bold above), in order of how many paths they cut:
1. **Anything → plant**: no entity exists. This cuts the US FDA, NSQ and approval paths and every "where is it
   made" question.
2. **Company → group**: only 158 companies belong to the 86 curated groups. The other 15,522 have no group, so
   group-level rollups and tickers cover 14.4% of the market by SKU count.
3. **Regulatory record → product**: NSQ, SEC, approval, NPPA retail and tender rows never point at a SKU, only
   at text, a company or a molecule.
4. **Registration and launch text → molecule and company**: brand registry, brand first-seen, CDCI supplier and
   approval applicant are unresolved, which kills the "first listing" and launch hops.
5. **Events link to one entity at most**: an NSQ event links to the company or nothing, never to the molecule,
   product and group as well.

### Path tests

Counts at each hop. A hop "passes" when the next entity is resolvable from the stored links alone.

**P1. NSQ batch → product → molecule → maker → group → ticker → price reaction → news** (NSQ listings since Jan 2025, n = 4,770)

| Hop | Records still connected | Breaks because |
|---|---:|---|
| NSQ → product | 0 linked (≈14% resolvable) | NSQ lists product text + manufacturer, not the marketer's SKU; nothing matches the (maker, molecules, strength, form) |
| NSQ → molecule | 4,218 (88%) | works |
| NSQ → maker (company) | 2,425 (51%) | the manufacturer string is resolved against the *marketer* table; contract makers often aren't in it |
| maker → group | 220 (4.6%) | contract manufacturers and small firms belong to no group |
| group → ticker | 90 (1.9%) | — |
| ticker → price window (45 days) | 90 | works once reached |
| group → news (±60 days) | 89 | works once reached |

Verdict: breaks at the first hop and again at maker → group. The large listed groups' quality record is mostly
invisible, because their batches are made by contract manufacturers named on the label.

**P2. SEC item → molecule → approval → brand registration → NPPA price → first listing** (SEC items since Jan 2024, n = 4,531)

| Hop | Connected | Breaks because |
|---|---:|---|
| SEC → molecule | 2,926 (65%) | free-text drug names, combination strings |
| → CDSCO approval, same molecule set, later date | 1,319 (29%) | approvals carry no SEC file number; matched by molecule set only (approximate) |
| → brand registration | **0** | `brand_registry` has generic text only (95% filled), never resolved to molecules |
| → NPPA retail price, same molecule set | 436 (10%) | works where NPPA notified a new-drug price |
| → a listed product with the same molecule set | ≈73% exist (local copy) | but there is no launch date: `brand_first_seen` links to no company or molecule (39 post-baseline rows) |

Verdict: breaks at the brand registration hop, and "first listing" has no date to report.

**P3. US FDA action → plant → company → group → ticker → US applications** (n = 630, 272 Indian)

| Hop | Connected | Breaks because |
|---|---:|---|
| action → plant | **0** | no FEI number or address stored; no plant entity |
| action → group (by firm name) | 49 (18% of Indian) | firm names are plant-level legal names ("XYZ Ltd Unit II") |
| group → ticker | 38 | — |
| group → US applications | 45 | works once reached |
| action → molecule | 0 | recall / alert subject text is not resolved |

Verdict: the plant hop does not exist, and the name shortcut misses 82% of Indian actions.

**P4. Tender rate → molecule → product → maker → quality record** (n = 7,453)

| Hop | Connected | Breaks because |
|---|---:|---|
| rate → molecule | 4,890 (66%) | generic item text; RMSCL best (77%), TNMSC and HMSCL weakest (~60%) |
| rate → supplier company | 3,171 (43%) | supplier names unresolved for the rest |
| → a product the supplier sells with that molecule | 1,054 (14%) | needs both of the above; no strength or form match |
| → supplier's NSQ record | 2,581 have any NSQ | the record is the supplier's, not the tendered product's |

Verdict: thin. Quality cannot be shown per tendered item, only per supplier.

**P5. Patent / exclusivity → molecule → US and India generics → launch** (molecules with an unexpired US patent, n = 518)

| Hop | Connected | Breaks because |
|---|---:|---|
| patent → molecule | 66.8% of patent rows (605 sets) | the rest name molecules absent from our catalog (US-only drugs) |
| molecule → US ANDA generics | 417 (80%) | Orange Book is held but never surfaced |
| molecule → India products | 518 (100% by construction) | — |
| India launch date | ≈98 (weak proxy) | no India patent data; new-brand sightings are unlinked |

Verdict: the US half works in the database but is invisible in the product; the India half is missing.

## 3. Profile completeness

| Entity | Shows today | Should also show (data already held) |
|---|---|---|
| Product | composition, prices, equivalents, label, interactions, price history (3 pts), mfr price, NPPA ceiling/notified, Jan Aushadhi, NSQ by same maker/molecule, bans, brand registry, procurement, pharmacology | first-listed date (`products.first_seen`), the maker and plant as an entity (`manufacturer_raw`), SEC and approval history of its composition, US/EU status and patent expiry of its molecules (Orange Book, patents, EMA), trials, an event timeline, news mentioning the brand |
| Molecule | very full: combos, share, NSQ, bans, shortages, approvals, SEC, trials, ceiling history, procurement, CDCI, global, PvPI | US patents and exclusivity dates, Orange Book generic holders (count and who), NDC count, WHO-PQ holders, a price trend across years, a launch timeline (new brands per quarter), news (only 10% of news resolves to molecules) |
| Combination | brands, share, ban, Jan Aushadhi, procurement, related | NSQ batches for the combination, SEC/approval history for the exact FDC (the rationality record), bans resolving (70% of bans don't reach a combo), price spread over time |
| Legal company | portfolio, NSQ, banned SKUs, tenders, debarments, licences, top brands | US FDA actions, SEC items (56% of SEC rows carry a company), approvals, trials, news, mfr price list, NPPA launch prices (73% carry a company), CDCI/brand-registry brands, its group, the plants it makes in |
| Group | now the deepest: dossier tabs, financials, risk, pipeline, portfolio | plants and their inspection history, mfr price lists and NPPA launch prices, Orange Book generics, filings by topic (plant, deal) as structured items, people, shareholding |

**Pages that don't exist:** NSQ batch, SEC item, approval, brand registration, trial, tender line and buyer,
US application and patent, news item, regulator document, plant, NPPA notification, event. Each record can only
be seen inside someone else's list, so "any fact from any other" fails at the first click.

**Collected but never surfaced, or barely:**
- `us_orange_book` (48,865): not read by any endpoint.
- `cdci_brand` (93k) and `cdci_supplier` (8k): only the generic and substance tables are used.
- `brand_first_seen`: only the Pipeline "new brands" tab.
- `reg_approvals.sites`: plant addresses for 92% of approvals, never parsed.
- `products.manufacturer_raw`: shown as a text field on the product page, never treated as an entity.
- `corp_announcements` topics deal, plant, approval and usfda: shown as a raw filings list, never attached to
  molecules or plants.
- `fin_results` and `results_calendar`: group pages and Specs only, not on the legal-company pages of a listed
  group's entities.
- `quote_history`: group page only.
- `segment_share`: a single snapshot, so no share history.

## 4. Missing domains

Licence classes match `docs/LICENSING.md`. Effort: S is up to 2 days, M up to 2 weeks, L longer.

| Domain | Source | Licensing / legal | Effort | Connects to |
|---|---|---|---|---|
| **Plants / manufacturing sites** | parse what we hold (`manufacturer_raw`, NSQ manufacturer, approval `sites`, US FDA firm); add the US FDA Data Dashboard (inspections, FEI, 483 classifications) and FDA establishment registration | ours (derived) + Open (FDA) | M | product, NSQ, approval, US FDA action, company, group, CDCI supplier |
| **API supply chain (DMFs, CEPs)** | US FDA DMF list (quarterly XLS: holder, subject, status); EDQM CEP database; WHO-PQ APIs | Open (FDA); EDQM terms to check | S for DMF, M for CEP | molecule ↔ API maker ↔ plant ↔ group; "who supplies the API" |
| **Patents, India** | Indian Patent Office journal (weekly PDFs); InPASS search is CAPTCHA-gated | journal: government publication, likely Gazette-like (confirm); no CAPTCHA bypass | L | molecule, company, launch timing, litigation |
| **Key people / KMP** | NSE filings (appointments and cessations already tagged); annual reports; MCA21 director data | NSE: Internal; MCA master data is paid and its terms restrict redistribution | S from filings, L from MCA | group, company, governance flags |
| **Shareholding** | NSE / BSE quarterly shareholding pattern (XBRL) | Internal (NSE data policy) | S–M | group, ticker; promoter pledge as a risk flag |
| **Unlisted company identity** | MCA company master (CIN, status, incorporation, registered office) | free basic search is CAPTCHA-gated; bulk data paid | M (paid) | company dedupe, singleton groups, plant addresses |
| **Exports / imports** | Commerce TradeStat (HS-level, free); company-level shipment data is commercial (Volza, Zauba: ToS forbid scraping) | product-level aggregates Open-ish; company-level blocked | S for HS, blocked for company | molecule (HS ↔ API mapping), country |
| **Court cases** | Indian Kanoon API (paid per call, commercial terms); eCourts (CAPTCHA); NCLT cause lists | IK: licensed per use; eCourts: no bypass | M | company, group, patent, governance |
| **More state tenders** | KMSCL Kerala, MPPHSCL, BMSICL Bihar, CGMSC; CPPP eprocure; GeM | Permission class (state corporations); GeM terms to check | M (per state S) | molecule, product, company, quality |
| **Inspections, India** | CDSCO risk-based inspection reports (occasional PDFs); state licence suspensions/cancellations | Permission | M | plant, company |
| **Pharmacopoeial standards** | IP / USP monographs | copyrighted and sold by IPC / USP: titles and status only | S (titles) | molecule, NSQ reason codes ("assay", "dissolution" per IP) |
| **Manufacturing licences** | state drug controller ODLS / SUGAM licence lists | Permission | M | plant, company, product licence number (CDCI and brand registry already carry licence numbers) |
| **Credit ratings** | CRISIL / ICRA / CARE / India Ratings rationale PDFs (filings already flag them) | publisher copyright: store rating, outlook and date with a link | S | group, company |
| **PLI / bulk-drug-park beneficiaries** | Department of Pharmaceuticals / PIB lists | Gazette or government notices | S | group, molecule (API), plant |
| **Prescription / sales volume** | IQVIA / AWACS | commercial licence only | blocked | everything (replaces our share estimates) |

## 5. Foundation problems, ranked by depth unlocked

| Rank | Problem | Evidence | What fixing it unlocks |
|---|---|---|---|
| 1 | **No maker / plant entity** | 17,262 maker strings on 82% of SKUs; NSQ manufacturer on 91% of batches; sites on 92% of approvals; 272 Indian FDA actions | P1 and P3 end to end; contract-manufacturing map (who makes for whom); quality per plant; US FDA risk on every product made at a flagged site. Edges to 6 entity types |
| 2 | **Company identity and grouping** | company → group 1%; top unlinked include 1,000+ SKU firms; junk company "pr" with 760 SKUs; mfr labels split "Emcure / Emcure Pharma / Emcure Pharmaceuticals" | every rollup (market share, quality, tenders, launches) for the 86% of SKUs outside curated groups; approvals (3% → most), brand first-seen (0% → most), procurement (43% →) |
| 3 | **Text → molecule resolution not applied everywhere** | brand registry 0% (95% have generic text), brand first-seen 0%, US FDA actions 0%, trials 40%, news 10%, SEC 69%, tenders 66% | P2 brand-registration hop; launch timeline per molecule; FDA actions on the molecule page |
| 4 | **Regulatory records never resolve to SKUs** | NSQ → product 0% (14% resolvable now); NPPA retail, tenders, SEC: 0 | "has this exact product failed?" on product pages and shelves; tender item ↔ SKU quality |
| 5 | **Launch dating** | `brand_first_seen` 183k rows, 39 post-baseline, unlinked; `products.first_seen` not shown | first-listing hop (P2, P5); new-launch counts per molecule, company and therapy |
| 6 | **Events link to a single entity** | 52% have any entity; none have more than one | every profile's timeline; watchlist alerts on molecule and product, not just group |
| 7 | **Pack-size mixing in price history** | 8% of products with 2+ observations jump ≥1.8× between sources | honest price trends, unit-price trends per molecule, NPPA compliance checks |
| 8 | **Banned FDC → combination** | 29.9% resolve | ban exposure per company and group; shelf checks on combinations |
| 9 | **Molecule hygiene** | 1,959 of 5,006 molecules occur in a single product (brand glued to a salt, typos) | cleaner joins for everything above; ATC 51% and ChEMBL 32% rise once junk is merged |
| 10 | **No record pages / generic edge store** | 12 record types without pages | the "any fact from any other" property itself |

## 6. Persona sanity check

| Persona | Cannot answer end to end today | Missing link or domain |
|---|---|---|
| Investor | "Which plants of Sun make products that failed NSQ, and were they US FDA-inspected?"; "How exposed is Cipla's US business to plants with import alerts?"; "What did Lupin launch in India this quarter?"; "Who supplies the API for Aurobindo's top ANDAs?" | plant entity; launch dating; DMF domain |
| Procurement | "Is the L1 supplier's *tendered product* clean, and who actually makes it?"; "Which alternative suppliers hold a licence and have no NSQ for this molecule?" | tender → SKU; maker / plant; licence domain |
| Regulatory affairs | "From SEC recommendation to approval to first brand to NPPA price: how long, by molecule?"; "Which approved FDCs later got banned?"; "Which sites appear on approvals and in NSQ?" | SEC ↔ approval file number; brand registry → molecule; ban → combo (30%); plant |
| Researcher | "Patent expiry → number of Indian brands launched in the following year"; "Do NSQ failure rates differ between contract manufacturers and own plants?"; "Price trend per unit across 2022–2025" | India patents; launch dating; maker / marketer split; pack normalisation |
| Developer | "Give me everything about entity X with stable links to neighbours" via the API: record types without ids or pages cannot be addressed; the catalog spine is not sellable (non-commercial sources) | generic edge store + record ids; sellable catalog rebuilt on CDCI + Form V + Gazette (licensing blocker) |

## 7. Roadmap ranked by link density

Score = new paths and profile fields unlocked ÷ effort (S = 1, M = 3, L = 8). The licence column flags items
where the data's terms, not the engineering, set the ceiling.

| # | Item | Effort | New edges / fields | Paths fixed | Score | Licence |
|---|---|---|---|---|---:|---|
| 1 | **Edge table + record pages**: one `links(src_type, src_id, dst_type, dst_id, method, confidence)` table fed by every connector; generic record page for NSQ, SEC, approval, trial, tender, US app, news, event | M | every existing link becomes navigable both ways; 12 page types | all five (navigability) | very high | — |
| 2 | **Maker / plant entity** from held text (manufacturer_raw, NSQ, approval sites, FDA firm, CDCI supplier) with address-based clustering | M | product, NSQ, approval, FDA action, company, group → plant | P1, P3 | very high | ours |
| 3 | **Company resolver + singleton groups**: alias table from name_index, legal-suffix normalisation, junk-company cleanup, every company defaults to its own group | S–M | approval → company, brand first-seen → company, procurement, NSQ, mfr labels | P1, P2, P4 | high | ours |
| 4 | **Run the molecule resolver over brand registry, brand first-seen, FDA actions, trials, news, tenders** | S | 5 tables gain molecule links | P2, P5 | high | — |
| 5 | **Launch dating**: link brand first-seen to company + molecule (+ product), surface `products.first_seen`, "new brands" per molecule and company | S | first-listing hop; launch fields on 3 profiles | P2, P5 | high | brand registry: Permission |
| 6 | **Surface Orange Book + patents + EMA on molecule and product** | S | patent expiry, US generic count and holders, EU status | P5 (US half) | high | Open / Attribution |
| 7 | **NSQ → product resolver** (maker + molecule set + strength + form; batch format per maker) | M | product-level quality record; shelf accuracy | P1 | medium-high | NSQ: Permission |
| 8 | **US FDA Data Dashboard (inspections, FEI, 483s)** joined to plants | M | inspection history per plant, group, product | P3 | medium-high | Open |
| 9 | **Multi-entity events**: write every resolvable entity per event (molecule, combo, company, group, plant) | S | timelines on all profiles; watchlist on molecules and SKUs | — | medium-high | — |
| 10 | **US DMF list** → molecule ↔ API maker ↔ plant | S | API supplier per molecule, backward-integration flag per group | new path | medium-high | Open |
| 11 | **Unit-price normalisation** of price history (pack-aware) | S | price trends on product, molecule, combo | — | medium | catalog: Internal |
| 12 | **Ban → combo** matcher (salt-form tolerant) | S | ban exposure | — | medium | Gazette |
| 13 | **SEC ↔ approval by file number / applicant** | S–M | SEC outcome → approval lag | P2 | medium | Permission |
| 14 | **Shareholding + KMP from NSE filings** | S–M | promoter holding, pledges, people on group pages | — | medium | NSE: Internal |
| 15 | **More state tenders** (KMSCL, MPPHSCL, BMSICL, CGMSC, CPPP) | M | procurement depth | P4 | medium | Permission |
| 16 | **India patent journal parsing** | L | India patent expiries | P5 India half | medium-low | to confirm |
| 17 | **Sellable catalog rebuild** (CDCI + Form V + Gazette prices) | L | developer view becomes possible | — | strategic | **blocker today** |
| 18 | Court cases (Indian Kanoon API) | M | litigation per company and patent | — | low-medium | paid licence |
| — | Company-level exports, IQVIA volumes | — | — | — | — | **blocked** (commercial) |

## The 10 highest-leverage links to build

1. **Record ↔ record edge store**, with every record type addressable and given a page. This creates unison
   itself, and every link below becomes navigable both ways.
2. **Product → maker/plant** (from `manufacturer_raw`, 82% of SKUs).
3. **NSQ batch → maker/plant**, and then → product (91% carry a manufacturer; 14% resolve to a SKU today).
4. **Company → group for all companies**, via singleton groups plus an alias resolver.
5. **Approval → company and → plant**, via applicant and the `sites` addresses (92% populated, 3% linked).
6. **US FDA action → plant (FEI) → group** (Indian actions: 18% reach a group today).
7. **Brand registry / brand first-seen → molecule + company**, which turns on launch dating (0% today).
8. **Molecule → Orange Book generics and patent expiry** on profiles (held, never shown).
9. **Event → all its entities** (52% have one today; none have more).
10. **Molecule → API maker** (US DMF list).

## Questions for you

1. **Should a plant be its own first-class entity, with addresses clustered into sites, or should we stop at
   "manufacturer company"?** Sites unlock the US FDA and NSQ paths properly, but cost roughly twice as much and
   need address matching.
2. **May every unlinked company become its own single-member group?** That makes company → group 100% and all
   rollups complete, at the cost of 15k tiny "groups" in group lists, which would be filtered by size. The
   alternative is to keep groups curated and show company-level rollups instead.
3. **For the developer view, do we start the sellable catalog rebuild (CDCI + Form V + Gazette) now, in
   parallel with the linking work, or wait for the CDSCO/NPPA permission replies?** The rebuild is the only path
   to an API that can expose the product spine; the linking work is useful either way.
