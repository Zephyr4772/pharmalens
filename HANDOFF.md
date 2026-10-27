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
- **DrugSetu**: trial key in `.env` (5 items/page, ~1 req/s, limited quota). `drugsetu_harvest` copies the full catalog (resumable cursor in `drugsetu_state`) into `drugsetu_products` + `data/sources/drugsetu/*.jsonl.gz`; build_core merges it into the catalog; product pages fall back to the saved copy. On quota/auth refusal the API is paused 6 h (`drugsetu_state.paused_until`).
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
- **Waiting on the user:** enable the relay task (one PowerShell command, see the final report); a Telegram bot token for failure alerts.

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
5. Then: retire `drugsetu_harvest` / `drugsetu_launches` and the product page's DrugSetu live lookup.

## Next candidates
0. Register at nrces.in for official CDCI files (`CDCI_BASE_URL`). Review leftover one-product junk molecules (e.g. brand glued to a molecule: 'Vensat Bioamoxycillin').
1. CTRI direct (search is CAPTCHA-protected; currently via ClinicalTrials.gov cross-registration). SEC rows from committees with non-standard tables (~107 'other').
2. OCR for scanned CDSCO NSQ PDFs (0-row months listed in the feed note).
3. E-pharmacy price refresh beyond DrugSetu, within rate limits. Court-stay tracking for bans.
4. USFDA warning letters (fda.gov blocks curl; import alerts are done via accessdata.fda.gov). More state procurement (KMSCL Kerala, others), WHO DDD values, PvPI signal reports.

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
