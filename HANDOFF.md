# PharmaLens v4 — work-in-progress handoff

Paused 2026-10-15 for a PC restart. Everything below is committed in git (`D:\pharmacopy\pharmalens`).

## What exists and works
- **Data** (`data/`, gitignored): Kaggle sources in `data/sources/kaggle/` (Indian Medicine Master Dataset Sept 2026 = spine,
  1mg 2025 scrape = newer MRPs/in-stock), legacy JSON in `data/sources/legacy/`, DuckDB at `data/pharmalens.duckdb`.
- **Core build**: `cd backend && py -3 -m pharmalens.pipeline.build_core` (~40 s): 543k SKUs, 6.9k molecules, 34k salt combos,
  15.9k companies, 74 parent groups (`backend/pharmalens/seed/parents.json`). Rebuild drops only core tables.
- **Connectors** (`backend/pharmalens/connectors/`, run `py -3 -m pharmalens.connectors list|run <name>|run all`):
  cdsco_nsq, nsq_mirror (Health Master, post-Aug-2025 months), banned_fdc, cdsco_gazette, cdsco_alerts, nppa_orders,
  jan_aushadhi (guest-token API), nse_quotes, nse_fundamentals, pharma_news, openfda_recalls. All ran OK; DB is populated
  (4.2k NSQ batches to 2026-08, 690 ban notifications, 2.4k Jan Aushadhi, 2k regulator docs, quotes, news).
- **Derived** (`derived.py`): product-level ban matching (strength + dosage-form aware; ban_level exact/review),
  market-share estimate (MRP × availability × listing reach, rolled up to parent group) + HHI → `segment_share`, `segment_stats`.
- **API**: FastAPI `pharmalens.api.main:app` (routers: catalog, market, regulatory, live incl. SSE `/stream`, shelf).
  Scheduler runs in-process. Launch config: `D:\pharmacopy\.claude\launch.json` → name `pharmalens` (port 8000).
  All endpoints smoke-tested 200 and <300 ms.
- **Web** (`web/`, React+TS+Vite): shell + screens written: Market, Regulatory, Shelf, Screener, Molecules, MoleculeDetail,
  Combos, ComboDetail, Groups, GroupDetail, CompanyDetail, ProductDetail; components ui.tsx, Share.tsx, Dossier.tsx.

## Remaining steps (in order)
1. Write missing screens referenced by `web/src/App.tsx`: `Equities.tsx`, `News.tsx`, `Feeds.tsx` (connector health table from
   `/meta/feeds` with "run now" → POST `/admin/connectors/{name}/run`, plus methodology section `#method`), `Watchlist.tsx`
   (uses `state/watchlist.ts` items + `/events` filtered by entity).
2. Add CSS for new classes used in screens: stack, tabs, pager, ev/ev-*, topic-*, kpi-*, b-mute, tape-warn, rail-dot, mkt-pill,
   topbar-right, sb-link, note, banner(-crit/-warn), shelf-row/flag-*, code textarea, filebtn, row-gap, inline-bar, kv, news-row, tall, panel-right, sortable.
3. `cd web && npm run build` → fix TS errors; server serves `web/dist`. Verify in browser pane (preview_start `pharmalens`).
4. Fix build_core: `dosage_form` sometimes contains junk ("Strip Of 10 Tablet Sr…") — re-derive from name when it contains "strip of"/"bottle of".
5. Write `docs/METHODOLOGY.md` + README (sources, cadence, market-share method, ban-matching caveats: court stays not tracked).
6. Next connectors: CDSCO approved new drugs / SEC minutes, NLEM 2022 PDF → molecules.is_nlem, NPPA 2026 price compendium
   (encrypted HIS dashboard; try via browser), CTRI trials, e-pharmacy price refresh scraper, USFDA warning letters/import alerts.
7. DrugSetu: docs need a dashboard login; API keys are in `.env` (gitignored). Need the user to export the OpenAPI JSON
   from https://app.drugsetu.com/app/docs (logged in) to wire it up.

## Gotchas
- DuckDB is single-writer: stop the server before `build_core`; CLI connector runs delegate to the server if it is up.
- DDL must run outside transactions (see `derived.migrate()`).
- Bash heredocs with apostrophes break in this environment — write scripts to files instead.
- Never kill python by image name; stop the server via preview_stop or its PID.
