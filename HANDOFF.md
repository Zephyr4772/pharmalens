# PharmaLens v4: handoff

Last updated 2026-10-17. All work is committed in git at `D:\pharmacopy\pharmalens`. See README.md and docs/METHODOLOGY.md.

## State
- **Working end to end**:
  - Catalog build
  - Alerts: subscriptions (watchlist / shelf list / filters) → Telegram, email, webhooks, in-app inbox, daily digest; dispatcher job every 2 min + right after any feed lands events
  - 32 connectors (all OK), incl. CDSCO approvals, SEC recommendations, NLEM 2022, ClinicalTrials.gov India, NPPA compendium
  - Data expansion (2026-10-17, see docs/SOURCES.md):
    - CDSCO portal JSON: NSQ/spurious Jan 2019 → Aug 2026 (6,645 rows, replaces PDF/mirror rows per month); approvals DB 2018 → Oct 2026 with sites and divisions; Rule 84AB brand registry (90,425 brands → licensed firm + licence no.)
    - CDCI 2026-07 (186k rows; 1,970 substances linked to molecules), mirror copy until NRCeS credentials are set
    - State procurement: TNMSC (17 tender pages, 5,962 supplier rates with order share) and RMSCL (2,042 contracts)
    - International: openFDA bulk (29k applications, 49k Orange Book, 20k patents, 138k NDC), WHO PQ (655), EMA (2,754), FDA Import Alert 66-40 (467 firms, 110 India), WHO product alerts (82)
    - NSE filings (42,666 announcements across tracked groups)
    - Molecule enrichment (ChEMBL + openFDA label + FAERS): all 3,097 molecules with 3+ SKUs, strict single-ingredient matching, PRR + co-reported drugs (OPENFDA_API_KEY set)
  - Integrity pass (2026-10-18, see METHODOLOGY 'Catalog integrity'): molecule repair (6,871 → 5,155 molecules), stable ids via `id_registry`, strict company matching, region-aware parent patterns, approvals linked by name only
  - New panels: molecule (pharmacology, FAERS, US label, procurement, global registrations, CDCI), product (procurement benchmark, brand registry, pharmacology), combo (procurement), group (filings, US/WHO footprint, tenders, licences), company (tenders, licences)
  - Derived ban matching and market share
  - FastAPI with SSE
  - All 13 terminal screens (incl. PIPE, ALERT) + detail pages, verified in the browser pane
- **Launch config**: `D:\pharmacopy\.claude\launch.json` → `pharmalens` (port 8010; serves `web/dist`). A copy is at `.claude/launch.root.json`.
- **Alert channels**: Telegram and email need `TELEGRAM_BOT_TOKEN` / `SMTP_*` in `.env`; webhooks and the inbox work without setup. Dispatcher tested end to end with a local webhook; Telegram/SMTP not tested against real accounts.
- **DrugSetu**: retired 2026-10-28 (trial over). Feeds and API client removed; `drugsetu_products` (456) and `data/sources/drugsetu/` kept, merged into the catalog by build_core, shown on product pages as a saved copy (`connectors/drugsetu.saved_record`). The `DRUGSETU_API_KEY` line in the server `.env` is now unused.
- **Catalog**: rebuilt after the last pattern change; nothing pending.

## Server (live copy since 2026-10-27)
- Azure for Students VM `srv1`, resource group `srv-rg`, India South Central (the subscription allows only uaenorth, eastasia, indiasouthcentral, koreacentral, indonesiacentral). B1ms (1 vCPU, 2 GB) with 4 GB swap, Ubuntu 24.04, Docker. About $19/month.
- SSH: `ssh -i ~/.ssh/azure_srv azureuser@172.198.57.15`. Port 22 is open only to the home IP (NSG rule `ssh-home`); update the rule when that IP changes. Azure CLI is at `D:\pharmacopy	oolszcli\Scriptsz.bat`; the university tenant requires MFA login.
- Layout: `/srv/<project>/{app,data,.env,docker-compose.yml}` (multi-project host; F1 goes in next). PharmaLens listens on 127.0.0.1:8010 inside the VM only.
- Deploy: build `web/dist`, ship `git archive` plus `web/dist` to `/srv/pharmalens/app`, then `docker compose up -d --build`. `deploy/Dockerfile` and `deploy/docker-compose.yml` are in the repo.
- **The VM is the live copy.** Do not run the laptop server with its scheduler against the same data. Catalog rebuilds happen on the laptop: copy `/srv/pharmalens/data/pharmalens.duckdb` down, rebuild, copy it back with the container stopped.
- Access: Tailscale only (private; tailnet account sinhalz4772@gmail.com). The dashboard is https://srv1.tailf3b6bc.ts.net, set up with `tailscale serve --bg --https=443 http://127.0.0.1:8010`; nothing is exposed publicly. Add more projects with `tailscale serve --https=<port>` or path prefixes.
- Backups: `/srv/bin/backup.sh` runs daily at 04:30 IST (app paused ~40 s) and keeps 7 nights in `/srv/backups`.
- All feeds were tested from the Azure IP on 2026-10-27 and none are blocked (CDSCO, NPPA incl. the encrypted dashboard, NSE, RMSCL, TNMSC, FDA, WHO).

## Depth pass (2026-10-27)
- **Prices:** `nse_history` holds full daily closes back to 1996 (≈245k rows, split-adjusted); group pages have 1Y/5Y/10Y/Max ranges.
- **SEC:** backfilled to 2015 (1,880 documents). A layout-independent parser re-parses every document (state `secparse|v2|<url>`), and outcome rules v3 reclassify by intent.
- **Products without labels** (~72%) show CDCI and US-label reference text at molecule level. Interaction lists are shared across brands with identical molecules (~1% → ~33% coverage).
- **Procurement:** Haryana HMSCL (358 contracts) added to Rajasthan and Tamil Nadu. UP UPMSCL blacklisting goes to `firm_debarments` via the home relay, because upmsc.in blocks cloud IPs.
- **Groups:** 12 new parent groups (`parent_sync` adds seed groups live). JB Chemicals is amalgamated into Torrent (seed `merged_into`); delisted tickers are skipped by the quote feed.
- **Safety:** PvPI drug-safety alerts 2016→2026 (193; dates parsed strictly). NPPA ceiling history covers 2011/2015/2022/2026.
- **News:** `news_archive` backfills GDELT month by month from 2017, about 12 h at its rate limit, every 2 h at :25.
- **Catalog:** 149 molecule spelling variants merged (5,155 → 5,006). `build_core` now keeps `product_info` (set `PHARMALENS_REBUILD_INFO=1` to regenerate); a rebuild takes ~1 min with no memory peak.
- **Tools:** `deploy/deploy.sh` (code), `deploy/rebuild.sh` (catalog rebuild cycle against the server database; server stopped meanwhile; old database kept as `.pre-rebuild`), `deploy/relay.ps1` (home relay + weekly backup pull to `D:\pharmacopyackups`). SSH via Tailscale: `ssh -i ~/.ssh/azure_srv azureuser@srv1`.
- **Relay task:** Windows task "PharmaLens relay" installed 2026-11-06 (daily 09:30, at logon, catches up on missed runs); runs `deploy/relay.ps1`, logs to `D:pharmacopy	mpelay.log`. The laptop must be on and on Tailscale at least once in 8 days or the UP blacklist feed fails (health alert at 6 days).

## DrugSetu replacement (agreed 2026-10-27, both items required)
DrugSetu's 7-day trial is over and a new account would also cap out (~500 queries), so it is a dead end. **Keep its
feeds and saved data (`drugsetu_products`, `data/sources/drugsetu/`, 456 products, 201 catalog prices) until our own
sources match it; only then retire it.** It was never the backbone: catalog prices come from the Kaggle master
(2022-24) and the 1mg 2025 snapshot; 143k active SKUs have no MRP. What DrugSetu gave per product, and our own route:
1. **Label & safety text** (uses, side effects, how it works, alcohol/pregnancy/breastfeeding/driving/kidney/liver)
   — share `product_info` across products with the same composition (same combo, prefer same strength and form),
   labelled as shared. **Done 2026-10-27:** product pages borrow the best donor (same per-molecule strengths, then
   same form) at read time; 150,520 → 455,283 active products (85%). Next: item 2.
2. **Official launch prices** — parse NPPA retail-price notifications / draft price calculation sheets
   (`reg_documents.doc_type = 'draft_price_sheet'`, 88 PDFs, newest 2026-10-19) into per-pack prices with company,
   formulation and date; add them to `price_observations` and the catalog.
   **Done 2026-10-27:** `nppa_retail_prices` feed parses the final Gazette notifications (current list + archive,
   2019 onwards; drafts skipped, Hindi-only editions give 0 rows): ~3,550 prices, 98% molecule-matched, 73% to a
   company. Shown on product pages (same molecules, own marketer/group first), REG desk "NPPA launch prices" tab,
   one launch event per new notification. Not written into catalog MRPs: they are per-unit, pre-GST ceilings for
   that marketer, not pack MRPs. Next: item 3.
3. **New-launch detection** — weekly diff of the CDSCO brand registry (Rule 84AB, 90k brands, licence + generic name)
   and CDCI brands (93k, `last_updated_on`) to emit launch events; replaces DrugSetu's newest-first listing.
   **Done 2026-10-27:** `brand_first_seen` (connectors/launches.py). The 84AB feed diffs each weekly snapshot (first
   run replays archived snapshots: 17 Oct = baseline, 27 Oct = 25 arrivals); CDCI records its per-brand date (baseline
   on first run). One summary launch event per run + one per arrival from a tracked group. PIPE tab "New brand
   registrations" (NEW vs LISTED in catalog). These are registrations, not launches; export brands appear too.
   CDCI only moves when its source updates (GitHub mirror of the 2026-07 release unless `CDCI_BASE_URL` is set).
4. **Price freshness beyond NPPA** — candidates to verify: GeM (Government e-Marketplace) listings, NPPA IPDMS
   Form V price lists, manufacturers' published MRP lists. No e-pharmacy scraping.
   **Assessed 2026-10-27:** GeM = generic government offer prices ("Brand: NA", fixed CPSE prices), not brand MRPs;
   at most a procurement benchmark. Pharma Sahi Daam / IPDMS (nppaipdms.gov.in) serves a **revoked TLS
   certificate** (CRYPT_E_REVOKED); not probed further. NB the existing `nppa_compendium` client already uses
   verify=False against that host — integrity risk, needs an owner decision. **Manufacturer Form V price lists are
   the real source**: Ipca publishes full lists on ipca.com (590 products; test: 54 matched SKUs had no MRP in our
   catalog, 19/86 moved >5%). Netmeds hosts an index of ~285 manufacturers' statutory Form V documents (2024–2026),
   incl. ~35 complete "New GST" lists from Sept 2025 (Cipla, Lupin, Sun, Torrent, Abbott, Zydus, Macleods, Leeford,
   Ajanta, Eris, Menarini, Sanofi, Natco…) and monthly lists (USV, Emcure, Ipca, Zuventus, Gennova). These are
   manufacturers' documents, but on an e-pharmacy domain: **owner decision pending** before using them.
   **Decided + built 2026-10-27:** owner approved the Netmeds-hosted manufacturer PDFs (company sites first; never the
   e-pharmacy's own product catalogue). `mfr_price_lists` feed (connectors/mfr_prices.py) parses every layout seen
   (statutory Form V; GST-revision sheets of Lupin, Sun, Macleods, Abbott, Zydus, Leeford, Torrent…) by header
   words, matches strictly (same group, brand+strength key, same dosage-form group, same or cleanly divisible pack,
   new price within 0.6–1.6x of ours / of the list's own pre-revision price, ambiguous = skipped), stores every row
   in `mfr_prices` (with PTR/PTS/GST), updates `products` MRP/pack/unit price when newer (`mrp_asof = 'mfr YYYY-MM-DD'`),
   adds `price_observations`, refreshes combo price stats (`derived.refresh_combo_prices`, shared with build_core),
   and build_core re-applies them on rebuild. Product pages show the manufacturer list entry with trade margins.
   Server backfill 2026-10-28: 182 lists, 51 manufacturers, 18,024 rows, 8,028 matched; ~5,850 catalog MRPs now
   from manufacturers (1,434 previously blank). Check: new/old MRP median ratio 1.00 (p5–p95 0.88–1.10).
   Open: Ajanta's list is a scanned image (needs OCR); Sanofi's PDF has no rows; ~15 small labels resolve to no
   company (Emcutix, Stedman, La Pristine, Modi Mundi, Gennova…) — add to parents/companies seeds to match them.
   Git: Windows credential manager lost the GitHub login; push with
   `git -c credential.helper= -c "credential.helper=!gh auth git-credential" push` (gh is signed in).
5. **Done 2026-10-28:** `drugsetu_harvest` / `drugsetu_launches` retired, product page shows the stored record only (no API calls). Data kept.

## Next candidates
0. Register at nrces.in for official CDCI files (`CDCI_BASE_URL`). Review leftover one-product junk molecules (e.g. brand glued to a molecule: 'Vensat Bioamoxycillin').
1. CTRI direct (search is CAPTCHA-protected; currently via ClinicalTrials.gov cross-registration). SEC rows from committees with non-standard tables (~107 'other').
2. OCR for scanned CDSCO NSQ PDFs (0-row months listed in the feed note).
3. More manufacturer price lists (OCR for scanned ones like Ajanta; seed the ~15 unrecognised companies). Court-stay tracking for bans.
4. USFDA warning letters (fda.gov blocks curl; import alerts are done via accessdata.fda.gov). More state procurement (KMSCL Kerala, others), WHO DDD values, PvPI signal reports.

## Investor-first terminal (2026-11-02, see docs/product-strategy.md)
- Primary user: investors / equity analysts. Build order: watchlist (done) -> Today + Companies (done) -> dossier
  tabs (done) -> Specs results desk (done) -> Specs results-day previews + weekly digest -> Signals / Calendar screens.
- Watchlist: `watchlist` table per Tailscale login (`watchlist.py`, `/api/v1/watchlist`), shared by terminal stars,
  Specs /watch /unwatch /watchlist, and the owner's "Specs: watchlist" alert subscription (Telegram).
- `api/routers/invest.py`: `/invest/today` (watchlist rows, ranked 7-day signals, results week, just reported,
  movers) and `/invest/companies` (one row per listed group: price, 1Y, P/E from trailing-4-quarter EPS, latest
  quarter YoY + margin, NSQ trend, US FDA, DPCO share, governance flags with /sanity thresholds; cached 5 min; CSV).
- Company dossier (`/g/<slug>`) has tabs: Overview (KPIs, price, event timeline, news), Financials (listed only:
  revenue/margin chart, quarterly + annual tables with YoY and EBITDA, peer ranks), Risk (sanity scorecard, NSQ per
  quarter, NSE disclosures, US FDA, quality and banned SKUs, debarments), Pipeline, Portfolio & business. Data from
  `/invest/dossier/<slug>` plus the existing `/parents/<slug>`.
- Terminal: `/` is now Today (key 1), `/companies` the screener (2); the old home moved to `/market` (3). Rail keys
  were renumbered (NEWS n, SHELF s, FEED f).

## US FDA inspections (2026-11-03): live
- Feed `fda_inspections` (weekly, Tue 06:40) pulls drug inspections and Form 483 citations from the FDA Data Dashboard
  API, using `FDA_DD_USER` / `FDA_DD_KEY` in the server .env (set with `deploy/set_keys.sh`). The first run loaded
  39,661 inspections and 38,178 citations. New OAI inspections of Indian firms raise `usfda` events.
- The sites linker places inspections on plants:
  - Indian inspections by locality or district; FDA gives no PIN, and the state is inferred from the city.
  - Inspections abroad only on sites that Indian approvals list.
  - Bioresearch Monitoring inspections only for known makers.
  - Inspections sharing an FEI go to the same site.
- Coverage: 72.5% of Indian inspections are linked (about 93% excluding Bioresearch Monitoring), and 699 sites have
  one. See `docs/fda-inspections-report.md` and `docs/link-samples/fda-inspections.md`.
- Scripting the dashboard's own Qlik export was refused as access circumvention: do not retry that.
- Feed `fda_compliance` (Tue 06:55, same key) loads drug warning letters and injunctions (all countries) and refused drug
  shipments from India into `fda_compliance_actions` / `fda_import_refusals`.
  - They're placed on plants by FEI first, and only onto sites other records define.
  - Coverage: 79.5% of Indian warning letters reach a plant, and 27% of refusals.
  - Site pages and plant lists show them, and the dossier's US FDA scorecard row counts them.
- The sites linker now also checks that a PIN fits a state the address names. See `docs/fda-inspections-report.md`
  (Known issues) and `docs/link-samples/fda-compliance.md`.

## Specs, the Telegram bot (2026-10-29)
- `bot/telegram.py` long-polls (messages + button taps), routes `/commands` to `bot/commands.py`, everything else to
  the agent (Gemini 3 flash -> 2.5 flash-lite -> Groq; tools in `bot/tools.py`). `deliver()` sends text with inline
  buttons, chart PNGs (`bot/charts.py`) and CSV files; scheduled jobs use it too.
- Name understanding: `bot/names.py` builds `data/name_index.json` (groups, companies, molecules, indices with short
  forms, tickers, nicknames, initials; fuzzy via rapidfuzz). Rebuilt daily by the `name_index` feed. Each message's
  names are resolved and appended for the agent; `resolve_names` tool for the rest; commands use `_find_group`.
- Commands: /brief /check /company /fin /sanity /compare /leaders /results /preview /digest /watch /unwatch
  /watchlist /chart /export /feeds /status.
- Results desk (`bot/desk.py`, feeds in `connectors/results_desk.py`): `results_preview` 07:45 (watched groups
  reporting today get a preview: last quarter, the year-ago quarter to beat, margin trend, stock, flags; others in
  one line), `results_summary` every 2h at :35 after `nse_results` (newest quarter per company, filed in the last 3
  days, once each via `desk|sum|<sym>|<date>` state; watched get a chart + season rank, the rest one batched
  message), `weekly_digest` Saturday 10:00. The watchlist subscription no longer sends plain results/results_due
  events (re-synced at startup).
- Briefings (`connectors/briefing.py`, 08:30 and 19:30) replace the old 2-hourly pulse; `bot/briefing.py` gathers
  facts and the model words them (template fallback). Quiet periods send one line.
- Financial data: `nse_results` feed parses NSE integrated-filing pages into `fin_results` (₹ crore) and board
  meetings into `results_calendar`; events `results` (YoY change) and `results_due`. Filing topics now include
  regulatory_action / litigation / mgmt_exit / credit (one-off retag on rule change, now `nse_topics|v3`: court-convened merger meetings are no longer litigation). Trial status / phase changes
  raise `trial` events (stopped = high).

## Gotchas
- **TLS.** Every feed verifies certificates (`pharmalens/tls.py`, `tls.CONTEXT`); never add `verify=False`. nppa.gov.in sends an incomplete chain, so Sectigo's DV R36 intermediate is pinned in `pharmalens/certs/` (it only helps reach public roots). If another site fails with 'unable to get local issuer certificate', pin its intermediate the same way (download from the URL in its certificate, check it with `openssl verify` against certifi). Revocation is checked weekly over OCSP by health_watch (errors retried hourly); nppaipdms.gov.in has served a certificate revoked as 'superseded' since 19 Oct 2026 (NPPA's slip, low risk).
- **Port 8010.** Another local app (node) uses 8000 on this machine.
- **NPPA compendium** client (`connectors/nppa_dashboard.py`) reproduces the dashboard's AES+RSA request wrapping; needs Origin/Referer headers or the CSRF call returns 'Session Expired'.
- **DuckDB is single-writer.** Stop the server before `build_core`. CLI connector runs delegate to the server when it is up.
- **No DDL inside transactions.** See `derived.migrate()`. `db.get_conn()` applies `schema.sql` (IF NOT EXISTS) on start.
- **Don't edit source through the shell.** Inline `py -c` and heredocs mangle `\b` and apostrophes in this environment, so write patch scripts to files.
- **Disk and memory.** A catalog build peaks at several GB of RAM (product_info step). DuckDB spills to `data/duckdb_tmp` and is capped at 3 GB (`PHARMALENS_DUCKDB_MEMORY`), but Python itself can still push Windows to grow `C:\pagefile.sys`. Close heavy apps before `build_core`, and run with `TEMP=D:\pharmacopy\tmp`. C: had under 10 GB free on 2026-10-18.
- **Never interrupt build_core casually.** It drops the core tables first. The ids survive in `id_registry`, but the catalog is empty until a build completes. Backups are in `data/backup_*`.
- **Connector CLI output is buffered** when redirected to a file: the JSON result lines appear only when the process exits.
- **CDCI files** have trailing tabs; read with `index_col=False` or every column shifts by one.
- **Stopping the server.** Never kill python by image name. Use `preview_stop` or the server's PID.
