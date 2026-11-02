# DrugDen product strategy

Analysis and planning only; no code was changed for this document. Evidence is cited by file path or table name.
Counts come from the server database backup of 2026-11-02 (`/srv/backups/pharmalens-20261102.tgz`) and the live API
(`/api/v1/meta/build`, `/api/v1/meta/feeds`) on 2026-11-02. Anything not verified is marked **ASSUMPTION**.

---

## 1. What exists today

### 1.1 The data

| Domain | Main tables (rows) | Time range | Granularity | Source |
|---|---|---|---|---|
| Product catalog | `products` 543,274 · `product_molecules` 807,478 · `combos` 40,185 · `molecules` 5,006 · `companies` 15,680 · `parents` 86 | prices 2022-24, mid-2025, Sept 2025–Aug 2026 | SKU (brand × strength × pack) | Kaggle master dataset (17 merged scrapes of 1mg, Apollo, Netmeds), 1mg 2025 scrape, manufacturers' price lists (`docs/SOURCES.md`) |
| Prices | `price_observations` 657,211 · `mfr_prices` 18,024 · `nppa_ceiling` 937 · `nppa_ceiling_history` 1,845 · `nppa_retail_prices` 3,550 · `jan_aushadhi` 2,439 · `procurement_rates` 8,406 | 2019 → today | per pack / per unit | catalog sources, Form V lists, NPPA Gazette, PMBI, 3 state corporations |
| Quality & bans | `reg_nsq` 10,019 (2019-01 → 2026-09) · `reg_banned_fdc` 690 · `firm_debarments` 42 · `pvpi_alerts` 193 · `usfda_actions` 627 | 2016 → today | batch / notification | CDSCO portal + PDFs, Gazette, UPMSCL, IPC, FDA |
| Approvals & pipeline | `reg_approvals` 4,027 (2002 → 2026-10-30) · `sec_items` 14,023 (2015 → 2026-10-22) · `trials` 2,012 · `brand_registry` 90,450 · `brand_first_seen` 183,469 | 2002 → today | approval / agenda item / trial / brand | CDSCO, ClinicalTrials.gov, CDSCO 84AB registry, CDCI |
| Global regulators | `us_applications` 29,420 · `us_orange_book` 48,865 · `us_ndc` 138,151 · `us_patents` 19,963 · `shortages` 1,578 · `who_pq` 658 · `ema_medicines` 2,754 | current | application / product | openFDA, WHO, EMA |
| Science | `molecule_enrichment` 2,542 · `product_info` 154,516 · `interactions` 7,472 · `cdci_*` (93k brands, 10k generics) | current | molecule / product | ChEMBL, openFDA labels + FAERS, Kaggle label text, CDCI |
| Markets & corporate | `quotes` 51 · `quote_history` 244,807 (1996 → 2026-10-30) · `fin_results` 940 (46 groups, Mar 2025 → Sep 2026) · `results_calendar` 876 · `corp_announcements` 41,046 | 1996 → today | daily close / quarter / filing | NSE (incl. via Yahoo) |
| News & events | `news` 60,156 (2017 → 2026-11-01) · `events` 2,253 | 2017 → today | article / event | publisher RSS, Google News, GDELT; derived events |
| Derived | `segment_share` 671,106 · `segment_stats` 30,145 | catalog build | therapy class / molecule / combination | `derived.py` (estimated value share, HHI) |

Events in the last 30 days: 634 news, 362 NSQ, 334 approvals, 170 price notifications, 162 recalls, 161 Gazette, 160
stock moves, 111 filings, 65 spurious, 22 bans, 15 results, 13 trial changes, 11 launches.

### 1.2 Collection, update and storage
- **43 scheduled feeds** (`backend/pharmalens/connectors/__init__.py`, `GET /api/v1/meta/feeds`). Regulators run daily
  (CDSCO 08:50–09:40, NPPA twice daily); quotes every 5 min; news every 15 min; results every 2 h; weekly feeds for
  WHO/EMA/brand registry/compendium; monthly for NLEM/CDCI. All healthy on 2026-11-02 except the weekly brand-registry
  scrape (its rerun was interrupted).
- **Storage**: one DuckDB file (1.25 GB) on a 2 GB Azure VM (B1ms), single writer, 600 MB DuckDB memory cap
  (`deploy/docker-compose.yml`). Raw responses archived under `data/raw/` and `data/lake/`. Nightly backups kept 7 days
  on the server and weekly on the owner's laptop (`HANDOFF.md`).
- **Catalog** is a batch build (`pipeline/build_core.py`, ~60 s, stable ids via `id_registry`); last build 2026-10-27.
  Prices then flow in live from manufacturers' lists (`connectors/mfr_prices.py`).
- **Integrity tooling**: molecule repair, strict company matching, ban/NSQ matching rules, TLS verification with
  weekly revocation checks, health alerts (`docs/METHODOLOGY.md`, `pharmalens/tls.py`, `connectors/health.py`).

### 1.3 Interfaces
- **Terminal** (React, `web/src/screens/`): 13 screens: MKT, REG, SHELF, PIPE, SCRN, MOL, FDC, CO, EQ, NEWS, FEED,
  WATCH, ALERT, plus product / molecule / combination / company / group profiles. Private over Tailscale; guests are
  read-only (`api/main.py` owner gate).
- **Internal REST API**: ~60 endpoints under `/api/v1` (OpenAPI at `/openapi.json`), CSV export on the main tables.
  No accounts, keys, metering or public exposure yet.
- **Specs (Telegram bot)**: free-text agent (SQL, news, web news, page reader) plus 13 commands (/brief /check /company
  /fin /sanity /compare /leaders /results /chart /export /feeds /status), charts, CSV files, AI briefings 08:30 and
  19:30, health alerts; owner-only (`bot/`).
- **Alerts engine**: watchlist / shelf-list subscriptions to Telegram, email, webhooks (`alerts.py`). **0 subscriptions
  exist**: the feature is unused.
- **Licensing gate**: per-table classes in `backend/pharmalens/licensing.py`; explained in `docs/LICENSING.md`.

### 1.4 Known quality issues and gaps (evidence)
| Issue | Evidence |
|---|---|
| **The catalog is not sellable** (non-commercial / unlicensed sources) | `docs/LICENSING.md`; master dataset `SOURCES.csv` says "treat it as non-commercial and share-alike" |
| 141,885 active SKUs (26%) have no price; 145,619 still on 2022-24 prices; only 5,849 on manufacturer prices | `products.mrp_asof` breakdown |
| 95,749 products (18%) have no company link; 56,427 (10%) no molecule link | `products.company_id`, `product_molecules` |
| Corporate grouping covers 86 groups / 158 companies of 15,680 | `parents`, `companies.parent_id` |
| Market share is an estimate from catalog weights, not sales | `docs/METHODOLOGY.md` §Market share |
| Ban court stays not tracked; ban matching needs pack checks | `docs/METHODOLOGY.md` §Ban matching |
| Some scanned CDSCO PDFs parse to 0 rows (2022-23) | `docs/METHODOLOGY.md` §NSQ matching |
| CDSCO permission needed for most CDSCO data; NSE and WHO data internal-only | `docs/LICENSING.md` |
| Price history mixes pack sizes between sources | `bot/charts.py` note; `price_observations` has no pack column |
| ASSUMPTION: results feed covers 46 of 48 listed groups; 2 small listings may file in a different format | `fin_results` distinct symbols |
| Infrastructure is a single 2 GB VM; LLM features run on free tiers (Gemini quota exhausted often, Groq fallback) | `deploy/`, `bot/llm.py`, server logs |

---

## 2. User landscape

| # | Segment | How they would use it | Fit today |
|---|---|---|---|
| 1 | **Pharma equity analysts and investors** (buy-side, sell-side, serious retail) | company risk and momentum: results, quality failures, US FDA, approvals, filings, pricing actions | strong (fin, sanity, filings, quality); needs depth |
| 2 | **Pharma strategy / competitive-intelligence / BD teams** (Indian majors, MNC affiliates, mid-size) | competitor launches, approvals, SEC, pricing, portfolio overlaps, market structure | strong on regulatory; weak on real sales |
| 3 | **Institutional procurement** (hospital pharmacists, trust hospitals, state medical corporations, GPOs) | fair-price benchmarks, cheaper equivalents, tender rates, banned/NSQ screening of supply | strong (SHELF, FDC spreads, procurement) |
| 4 | **Regulatory affairs and QA professionals; regulatory consultants; CROs** | NSQ trends by molecule/maker, bans, SEC decisions, approvals precedents | strong; needs search + history |
| 5 | **Public-health NGOs, access-to-medicine and policy researchers, academics** | price spreads, essential-medicine availability, quality failure patterns, AMR (antibiotic FDCs) | strong analytically; needs bulk data + citations |
| 6 | **Journalists and fact-checkers** (health, business, investigative) | story leads: spurious drugs, repeat offenders, price gouging, recalls of Indian exports | strong for leads; needs provenance links |
| 7 | **Health-tech developers** (e-pharmacies, HIS/EMR, telemedicine, PBM/TPA startups) | drug master data API: brand → composition → price → ban/NSQ flags | strong need; blocked by licensing + no API |
| 8 | **Insurers / TPAs / corporate health** | claims price checks, generic substitution savings, fraud (banned/NSQ drugs billed) | medium; needs bulk + API |
| 9 | **Distributors and retail chemist chains** | shelf compliance (bans, NSQ batches), margin (PTR/PTS), cheaper substitutes | medium; low willingness to pay per store (ASSUMPTION) |
| 10 | **Lenders, M&A advisors, auditors** | counterparty due diligence on pharma companies (quality, regulatory, legal) | medium; `/sanity` is the seed |
| 11 | **Educators and students** (pharmacy, public health, data science) | teaching datasets, case studies | low revenue, high reach (HF samples) |

---

## 3. Personas (top 7)

### P1. Priya Raman, pharma sector equity analyst (buy-side fund, Mumbai)
8 years' experience; uses Bloomberg/Capitaline, ACE Equity, company filings, AIOCD-AWACS summaries via brokers,
Excel. High Excel skill, light SQL.
- **Jobs**: spot earnings and regulatory risk before the market; build quarterly views on 20-30 covered companies;
  answer the PM's "what happened to X today?" in minutes.
- **Questions**: Which covered companies had US FDA import alerts or warning letters this quarter? Is Alkem's NSQ count
  rising and in which molecules? Which companies have the most SEC recommendations (future launches) this year? How
  exposed is Lupin's India portfolio to NPPA ceiling cuts? Who reports results this week, and what was YoY last
  quarter? Which companies disclosed regulatory orders or litigation? How did the stock react to past FDA actions?
  Which new launches did NPPA price for Mankind this quarter?
- **Workflow and pain**: regulatory signals are scattered across CDSCO PDFs, FDA sites and exchange filings; nobody
  ties a failed batch to a listed group automatically; Indian quality data is absent from Bloomberg.
- **Adopts if**: daily India-specific regulatory and quality signal mapped to listed groups, with history, in Excel/API
  and on the phone; faster than her juniors reading PDFs.
- **Leaves if**: wrong company mapping (a subsidiary missed), stale data, a false "red flag" in front of a PM, numbers
  that disagree with filings.
- **Must-have**: correct group mapping; event history with sources; results and filings; watchlist alerts; export.
  **Nice**: event–price-reaction studies; estimates of sales exposure; peer screens.

### P2. Rahul Mehta, competitive-intelligence lead (MNC pharma India affiliate, Gurugram)
12 years; uses IQVIA/AIOCD sales data (licensed), PharmaTrac, CDSCO site, consultants. Medium technical skill.
- **Jobs**: track competitor launches, approvals and pricing in his therapy areas; brief leadership monthly.
- **Questions**: Which brands of semaglutide / dapagliflozin combinations launched in the last 90 days, by whom, at what
  NPPA price? Who got SEC approval for X? How many marketers sell molecule Y, and how fragmented is it? Which new
  brands were registered by Sun in cardiology? Are competitors facing quality failures I can use in positioning? Which
  of my molecules face price-control risk (NLEM)?
- **Pain**: IQVIA is expensive and lags; regulatory sources are manual; launch tracking relies on field force anecdotes.
- **Adopts if**: earliest signals of competitor launches (SEC → approval → brand registration → NPPA price → first
  listing) in one timeline per molecule; exportable.
- **Leaves if**: coverage gaps in his therapy area; no real sales numbers; data he cannot cite internally.
- **Must-have**: molecule/therapy watchlists, launch timeline, exports, provenance. **Nice**: real sales data integration.

### P3. Dr. Meena Iyer, chief pharmacist, 600-bed trust hospital (Chennai)
Uses HIS formulary module, distributor quotes, TNMSC rate lists, phone calls. Low-to-medium technical skill.
- **Jobs**: buy safe medicines at fair prices; avoid banned and NSQ batches; justify formulary choices to the board.
- **Questions**: Is any batch on my shelf on a CDSCO NSQ or spurious list? Which of my items are banned FDCs? What
  is the cheapest quality-acceptable equivalent of brand X? What do state corporations pay for this molecule? What is
  the Jan Aushadhi price? Did the manufacturer of my top 20 items have quality failures this year?
- **Pain**: NSQ lists are monthly PDFs; matching batches by hand is impossible; prices vary 50× for the same molecule.
- **Adopts if**: upload the inventory once, get alerts whenever a new list affects it; a defensible price benchmark.
- **Leaves if**: false alarms on batches, missed real ones, prices that are years old.
- **Must-have**: SHELF with continuous re-checks (exists), current prices, tender benchmarks, simple UI. **Nice**:
  HIS integration, formulary report PDF.

### P4. Suresh Nair, regulatory affairs manager (mid-size Indian generics company, Ahmedabad)
Uses CDSCO SUGAM, consultants, Excel trackers of SEC minutes. Medium skill.
- **Jobs**: prepare applications with precedents; monitor bans and quality alerts in his portfolio; know what SEC
  decided for similar products.
- **Questions**: What did SEC decide on FDC X in the last 3 years and why? Which approvals exist for composition Y
  with strength Z? Is my FDC at risk under a ban notification? Which of our batches or molecules appeared on NSQ lists,
  and which labs flagged them? Have any of my competitors' similar products been deferred?
- **Pain**: SEC minutes are long PDFs in shifting layouts; approvals search on CDSCO is clunky.
- **Adopts if**: searchable SEC/approval history with outcomes and links; alerts on his molecules.
- **Leaves if**: outcome classification errors ("recommended" vs "deferred"), missing minutes.
- **Must-have**: SEC full-text search, approval search, precise ban matching, PDF links. **Nice**: precedent summaries.

### P5. Ananya Sharma, policy researcher (access-to-medicines NGO, Delhi)
Uses Stata/R/Python, government PDFs, RTI requests. High technical skill.
- **Jobs**: publish evidence on medicine prices, quality and policy (price control, FDC bans, AMR).
- **Questions**: How did prices of NLEM molecules change after ceiling revisions? What share of antibiotic FDCs on sale
  are banned or irrational? Which states pay the most for essential medicines? Which manufacturers have repeated NSQ
  failures? How do Jan Aushadhi prices compare with brands, by therapy class?
- **Pain**: no machine-readable national dataset; scraping is fragile; provenance matters for peer review.
- **Adopts if**: dated, versioned bulk downloads with a data dictionary, methodology and citation; free or cheap.
- **Leaves if**: unclear licensing, no versioning, unexplained changes between downloads.
- **Must-have**: bulk exports (CSV/Parquet), versioned releases, methodology, citation, licence clarity. **Nice**:
  notebooks, API.

### P6. Kabir Sen, investigative health journalist (national digital outlet)
Uses Google, RTI, sources, spreadsheets. Medium skill.
- **Jobs**: find and verify stories quickly.
- **Questions**: Which companies have the most spurious-drug reports? Who supplied the drugs that failed in state X?
  Are banned FDCs still on sale? Which exporters got FDA import alerts? Did the company that failed this batch also win
  state tenders?
- **Pain**: connecting regulator records across sources by hand.
- **Adopts if**: cross-linked records with original-document links; quick search; story-ready charts.
- **Leaves if**: a single wrong attribution that could become a correction or defamation risk.
- **Must-have**: provenance on every fact, original PDFs, careful wording ("listed as", not "guilty"). **Nice**: alerts.

### P7. Arjun Rao, backend lead (health-tech startup: e-pharmacy / HIS / TPA, Bengaluru)
Uses PostgreSQL, REST APIs, a scraped drug master. High technical skill.
- **Jobs**: maintain a reliable drug master (brand → composition → strength → price → flags) inside his product.
- **Questions** (as API calls): resolve a free-text drug name to a canonical product; get composition and molecule ids;
  is this product banned or NSQ-affected; cheapest substitutes; current MRP and pack; changes since date D.
- **Pain**: scraped masters break; licensing risk; no change feed.
- **Adopts if**: stable ids, a clear commercial licence, change feed/webhooks, uptime SLA, good docs.
- **Leaves if**: licence ambiguity, breaking schema changes, downtime, rate limits that don't fit his traffic.
- **Must-have**: API keys, metering, versioned schema, change feed, licence. **Nice**: SDKs, bulk sync.

---

## 4. Cross-persona synthesis

**What everyone needs (the core that must be rock solid)**
1. **Correct entity resolution**: product → composition → molecules; company → group. Every persona's trust breaks on
   a wrong link.
2. **Provenance on every fact**: source, document link, publication date, fetched date.
3. **Freshness that is visible**: per-dataset "as of" and feed health.
4. **Regulatory core**: NSQ/spurious, bans, approvals, SEC, recalls, price controls, mapped to companies and molecules.
5. **Search that understands loose names** (now in Specs; not yet in the terminal or API).
6. **Alerts on a watchlist** (molecules, companies, SKUs, inventory).
7. **Licence clarity**: what may be reused, and how to cite it.

**Persona-specific (modules / tiers / phases)**
- Investor module: results, filings, governance flags, stock reaction (P1, P10).
- Launch intelligence: SEC → approval → registration → NPPA price → listing timeline (P2, P4).
- Procurement module: SHELF, tender benchmarks, equivalents (P3, P8, P9).
- Research data: versioned bulk releases, data dictionary, citations (P5, P11).
- Developer API: keys, metering, change feed, stable ids (P7, P8).

**Conflicts and resolutions**
| Conflict | Resolution |
|---|---|
| Investors want terse signals; researchers want raw completeness | same data, two surfaces: signals in Specs/terminal, bulk in releases/API |
| Journalists need cautious wording; analysts want sharp red flags | flags always carry the record and wording "listed as / disclosed", never verdicts |
| Developers need stable schemas; we are iterating fast | version the public API separately (`/v1` frozen), internal API free to change |
| Commercial value sits in the catalog; the catalog is not sellable | sell regulatory + Gazette + manufacturer-price data first; rebuild a permitted catalog |
| Free tier for NGOs/students vs paid for firms | free: samples, citations, low row limits; paid: full API, alerts, exports at volume |

---

## 5. Gap analysis

| Need (personas) | Reality | Gap type | Severity |
|---|---|---|---|
| Sellable product master (P7, P8, P2) | catalog built from non-commercial / unlicensed scrapes | Trust (licensing) / Data | **critical** |
| Permission to resell CDSCO data (all paying) | not requested yet; drafts in `docs/outreach/` | Trust (licensing) | **critical** |
| Public API with keys, metering, docs (P7, P5, P1) | internal API only, no auth beyond Tailscale | Access | high |
| Current prices (P3, P2, P8) | 26% unpriced, 27% on 2022-24 prices; 5.8k on manufacturer lists | Freshness / Data | high |
| Correct company → group mapping (P1, P2, P6) | 86 groups; 18% products lack a company | Quality / Data | high |
| Real sales / market share (P1, P2) | estimates from catalog weights | Data | high (expensive to close) |
| Versioned, citable bulk releases (P5, P6, P11) | CSV exports of live tables; no versions/changelog | Trust / Access | high |
| Provenance on every row in exports/API (P5, P6, P7) | many tables carry `source_url`; not uniform | Trust | medium |
| Watchlist alerts actually used (all) | engine exists; 0 subscriptions; Specs has no /watch | Product | high |
| Terminal clarity / onboarding (all) | 13 dense screens; owner found it overwhelming | Product (UX) | high |
| SEC/approvals full-text search with precedent view (P4, P2) | tables + filters, no full-text search | Product / Access | medium |
| Launch timeline per molecule (P2) | data exists across tables; no unified view | Product | medium |
| Financial depth: balance sheet, segment revenue (US vs India), shareholding/pledges (P1, P10) | P&L only, 7 quarters | Data | medium |
| Ban court stays (P3, P4, P9) | not tracked | Data / Quality | medium |
| Scanned NSQ PDFs (P4, P5, P6) | some 2022-23 months parse to 0 rows | Data | low–medium |
| Uptime and scale for paying API users (P7) | single 2 GB VM, single DuckDB writer, free LLM tiers | Access / Product | medium (rises with users) |
| Change feed / webhooks for developers (P7) | events table internal; webhooks only via alert subs | Access | medium |
| Multi-user accounts, teams (P1, P2, P3) | owner + read-only guests over Tailscale | Product | high once selling |

---

## 6. Prioritized roadmap

Impact / Effort: H / M / L. **QW** = quick win.

### Now (next 2–4 weeks): make it trustworthy and usable for one primary persona
| # | Item | Personas | Impact | Effort | Depends on | |
|---|---|---|---|---|---|---|
| 1 | Choose the primary persona and positioning (see questions) | all | H | L | owner | QW |
| 2 | Send CDSCO / NPPA / state permission requests; register the entity | all paying | H | L | owner | QW |
| 3 | Watchlists everywhere: `/watch` in Specs + terminal stars → real-time alerts with context | P1 P2 P3 P4 | H | M | — | |
| 4 | Terminal redesign around the primary persona's 3–5 jobs (home, fewer screens, global name search) | all | H | M | 1 | |
| 5 | Expand corporate grouping (top 300 marketers by SKUs), fix company links for unlinked products | P1 P2 P6 | H | M | — | |
| 6 | Public "data status" page: coverage %, freshness per dataset, known limitations | all | M | L | — | QW |
| 7 | Uniform provenance fields (source, url, published_on, fetched_at) on every exported row | P5 P6 P7 | M | M | — | |
| 8 | Hugging Face sample (licence-clean subset: Gazette prices, bans, openFDA, CDCI) with data card | P5 P7 P11 | M | L | licensing.py | QW |

### Next (1–3 months): open the product
| # | Item | Personas | Impact | Effort | Depends on |
|---|---|---|---|---|---|
| 9 | Public API v1: accounts, keys, 500 rows/day free tier, metering, licensing gate, OpenAPI docs | P7 P5 P1 | H | M | 2, 8 |
| 10 | Sellable catalog rebuild from permitted sources (CDCI, Form V lists, NPPA, open Kaggle sets) | P7 P8 P2 | H | H | licensing |
| 11 | More manufacturer price lists: seed unrecognised companies, OCR scanned lists (Ajanta etc.) | P3 P8 P2 | H | M | — |
| 12 | Launch-intelligence timeline per molecule (SEC → approval → 84AB → NPPA → listing) | P2 P4 P1 | H | M | 5 |
| 13 | SEC / approvals full-text search with outcomes and precedent lists | P4 P2 | M | M | — |
| 14 | Versioned monthly releases (Parquet/CSV) with changelog and DOI-style citation | P5 P6 P11 | M | M | 7 |
| 15 | DrugDen website: landing, pricing, docs, sign-up (sinhal.space) | all | H | M | 9 |
| 16 | Financial depth: balance sheet, cash flow, segment revenue, shareholding and pledges from NSE filings | P1 P10 | M | M | — |

### Later (3–9 months): differentiate and scale
| # | Item | Personas | Impact | Effort | Depends on |
|---|---|---|---|---|---|
| 17 | Real sales data partnership (AIOCD-AWACS, Pharmarack) or a licensed NSE data agreement | P1 P2 | H | H ($) | revenue |
| 18 | Ban court-stay tracking; OCR backfill of scanned NSQ lists | P3 P4 P5 | M | M | — |
| 19 | Change feed and webhooks for developers; SDK | P7 P8 | M | M | 9 |
| 20 | Team workspaces: shared watchlists, inventory lists, Slack/Teams | P1 P2 P3 | M | M | 9, 15 |
| 21 | Natural-language queries in the terminal (Specs on the web) | all | M | M | 4 |
| 22 | Infrastructure for paying users: managed Postgres / read replica, paid LLM tier, uptime monitoring | P7 | M | M | 9 |
| 23 | More state procurement sources; CTRI (if CAPTCHA-free access appears) | P3 P4 | L | M | — |
| 24 | Regional languages for retail chemists | P9 | L | M | — |

---

## 7. Self-critique

**Probably underweighted**
- **Retail chemists and distributors (P9)**: the largest group by headcount, already served by SHELF, and the most
  exposed to NSQ/ban penalties. I treated them as low willingness to pay without evidence.
- **Insurers / TPAs (P8)**: claims-level price and fraud checks could be one of the few segments with budget and clear
  ROI. No persona was built for them.
- **Doctors** were left out deliberately (clinical-advice risk), but prescribers asking "cheapest equivalent" are a
  real audience for a consumer surface.

**Assumptions without evidence**
- That analysts value Indian quality data (NSQ) enough to pay: materiality to stock prices is unproven; an
  event-study would test it.
- Willingness to pay of every segment, and the price points; no user interviews have been done.
- That CDSCO / NPPA will grant permission, and that the Gazette (s.52(1)(q)) and Form V readings hold: not
  legal advice.
- That the free LLM tiers and a 2 GB VM suffice for early users.
- That market-share estimates "track IPM rankings closely" holds beyond the top 10 groups.

**What a sceptical user would still say is missing**
- "Your prices are a year or more old for most products; I can get today's price on any e-pharmacy app."
- "Without real sales numbers, your market share is a guess."
- "I can't build on data you're not allowed to sell me."
- "One wrong attribution of a spurious drug to my company and I'll sue" (defamation risk needs careful wording and a
  correction process).
- "Who are you?" No company, team page, uptime record or customers yet: trust takes time and references.

---

## Executive summary
1. DrugDen already holds an unusually complete picture of Indian pharma: 543k SKUs, 10k failed batches, 14k SEC items,
   4k approvals, 3.5k NPPA launch prices, 41k NSE filings, 7 quarters of results for 46 listed groups, refreshed by 43 feeds.
2. Its unique value is **linking regulator records to products, molecules and companies**, daily, with provenance.
3. The biggest blocker is licensing: the product catalog is not sellable, and most CDSCO data needs permission.
4. The second blocker is price freshness: 26% of SKUs unpriced, 27% on 2022-24 prices.
5. Strongest-fit personas: investors/analysts, competitive intelligence, institutional procurement, regulatory affairs.
6. Strongest reach personas: NGOs/researchers, journalists, developers; they need versioned bulk data and an API.
7. What everyone needs: correct entity links, provenance, visible freshness, watchlist alerts, licence clarity.
8. Now: pick the primary persona, send permission requests, ship watchlists, redesign the terminal around 3–5 jobs.
9. Next: public API with metering, sellable catalog rebuild, more manufacturer prices, launch timelines, website.
10. Later: real sales data, change feeds, team workspaces, scale infrastructure once revenue justifies it.

## Questions for the owner
1. **Who is the first paying customer** you want in the next 6 months: an investor/analyst desk, a pharma company's
   strategy/CI team, a hospital/procurement buyer, or developers via the API? This decides the terminal redesign and
   the website.
2. **Public good or paid product first?** Should DrugDen launch with open, citable releases (reputation with NGOs,
   journalists, researchers), or go straight to paid access for firms, with free use limited to samples?
3. **Are you ready to formalise**: register DrugDen as an entity, send the CDSCO/NPPA permission letters, and budget
   for a legal review (and later, licensed sales or NSE data)? Several "Now" items depend on this.

---

## Decision (2026-11-02): investors and equity analysts first

The owner chose persona P1 (investors / pharma equity analysts) as the first paying customer. Everything below is
designed for Priya's day; other personas keep their tools as secondary modules.

### Terminal: from 13 screens to 5 jobs
| New screen | Answers | Built from (exists today) |
|---|---|---|
| **Today** (home) | "What changed for the companies I follow, and what's coming?" Watchlist rows (price, change, latest signal badges, next results date), a ranked signal feed (results, US FDA, regulatory orders, quality failures, approvals/SEC, price notices) for listed groups, this week's results calendar, NIFTY Pharma and movers | MKT, EQ, events, `results_calendar`, quotes |
| **Companies** | "Which names deserve attention?" One screener of listed groups: price, 1y change, m-cap, P/E, revenue and profit YoY, margin, quality trend, US FDA actions, governance flags, DPCO exposure; sort, filter, star, export | CO, EQ, `fin_results`, `/sanity` logic |
| **Company dossier** | "Everything about X, in one place" Tabs: Overview (price chart with events overlaid), Financials (quarters, margins), Risk (sanity scorecard with sources), Pipeline (SEC, approvals, trials, NPPA launch prices, new brands), Quality (NSQ, FDA), Filings, News, Portfolio (therapy mix, price-control exposure) | group profile, `/fin`, `/sanity`, PIPE |
| **Signals** | "Show me every event of type T for companies C since D" Filterable tape with sources and CSV | REG, NEWS, events |
| **Calendar** | "What's scheduled?" Results dates, SEC meetings, NPPA notifications | `results_calendar`, `sec_items` |

Moved one click away under **Research**: product screener, molecules, combinations and price spreads, SHELF, alerts
setup, feeds (owner only). Global **Ctrl+K search uses the name index**, so "drl" or "glenmrk" works in the terminal too.

### Specs: an analyst in your pocket
- **/watch** companies (and molecules): real-time alerts only for the watchlist, each with context: "Alkem: 4th NSQ
  listing this quarter (molecules X, Y); stock −1.2% today; last results profit +12% YoY".
- **Results day**: a preview the morning a watched company reports (last 4 quarters, consensus-free trend), then a
  summary minutes after filing (YoY, margin change, anything unusual).
- **Weekly portfolio digest** (Sunday evening): for the watchlist, what changed in quality, regulatory, filings,
  financials and price.
- Briefings default to the watchlist first, the market second.

### Data priorities this implies
1. Group mapping for every listed pharma company and its subsidiaries (top of the list: correct attribution).
2. Results depth: balance sheet, cash flow, segment revenue (US vs India), shareholding and promoter pledges.
3. Event history usable for event studies (FDA action or NSQ spike vs. stock reaction).
4. Clear wording and source links on every flag ("disclosed", "listed as"), never verdicts.

### Build order
1. **Watchlist backbone**: one watchlist shared by terminal and Specs; `/watch`, `/unwatch`, `/watchlist`.
2. **Today** home and the **Companies** screener.
3. **Company dossier** tabs (reuse the existing group page; add Financials and Risk).
4. Specs results-day and weekly digests.
5. Signals and Calendar screens; move the rest under Research.
