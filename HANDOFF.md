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

## Next candidates
0. Register at nrces.in for official CDCI files (`CDCI_BASE_URL`). Review leftover one-product junk molecules (e.g. brand glued to a molecule: 'Vensat Bioamoxycillin').
1. CTRI direct (search is CAPTCHA-protected; currently via ClinicalTrials.gov cross-registration). SEC rows from committees with non-standard tables (~107 'other').
2. OCR for scanned CDSCO NSQ PDFs (0-row months listed in the feed note).
3. E-pharmacy price refresh beyond DrugSetu, within rate limits. Court-stay tracking for bans.
4. USFDA warning letters (fda.gov blocks curl; import alerts are done via accessdata.fda.gov). More state procurement (KMSCL Kerala, others), WHO DDD values, PvPI signal reports.

## Gotchas
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
