# PharmaLens v4: handoff

Last updated 2026-10-15. All work is committed in git at `D:\pharmacopy\pharmalens`. See README.md and docs/METHODOLOGY.md.

## State
- **Working end to end**:
  - Catalog build
  - 12 connectors (all OK)
  - Derived ban matching and market share
  - FastAPI with SSE
  - All 11 terminal screens + detail pages, verified in the browser pane
- **Launch config**: `D:\pharmacopy\.claude\launch.json` → `pharmalens` (port 8000; serves `web/dist`). A copy is at `.claude/launch.root.json`.
- **DrugSetu**: trial key in `.env`. 5 items per page, ~1 req/s, limited quota. The connector stops cleanly on quota errors.
- **Catalog**: rebuilt after the last pattern change; nothing pending.

## Next candidates
1. More government feeds:
   - CDSCO approved new drugs and SEC meeting minutes (CDSCO "Approval_new" / cdscoonline `cdscoAppDrugs`)
   - NLEM 2022 PDF → `molecules.is_nlem`
   - CTRI trials
2. NPPA 2026 price compendium: encrypted HIS dashboard. Try capturing its XHR through the browser pane.
3. OCR for scanned CDSCO NSQ PDFs (0-row months listed in the feed note).
4. E-pharmacy price refresh beyond DrugSetu, within rate limits. Court-stay tracking for bans.
5. Alerts: email or Telegram notification when an event matches the watchlist or a saved SHELF list.
6. USFDA warning letters and import alerts (fda.gov blocks curl; needs the browser or the FDA data dashboard).

## Gotchas
- **DuckDB is single-writer.** Stop the server before `build_core`. CLI connector runs delegate to the server when it is up.
- **No DDL inside transactions.** See `derived.migrate()`. `db.get_conn()` applies `schema.sql` (IF NOT EXISTS) on start.
- **Don't edit source through the shell.** Inline `py -c` and heredocs mangle `\b` and apostrophes in this environment, so write patch scripts to files.
- **Stopping the server.** Never kill python by image name. Use `preview_stop` or the server's PID.
