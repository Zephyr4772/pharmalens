# PharmaLens v4: handoff

Last updated 2026-10-15. All work is committed in git at `D:\pharmacopy\pharmalens`. See README.md and docs/METHODOLOGY.md.

## State
- **Working end to end**:
  - Catalog build
  - 17 connectors (all OK), incl. CDSCO approvals, SEC recommendations, NLEM 2022, ClinicalTrials.gov India, NPPA compendium
  - Derived ban matching and market share
  - FastAPI with SSE
  - All 12 terminal screens (incl. PIPE) + detail pages, verified in the browser pane
- **Launch config**: `D:\pharmacopy\.claude\launch.json` → `pharmalens` (port 8010; serves `web/dist`). A copy is at `.claude/launch.root.json`.
- **DrugSetu**: trial key in `.env`. 5 items per page, ~1 req/s, limited quota. The connector stops cleanly on quota errors.
- **Catalog**: rebuilt after the last pattern change; nothing pending.

## Next candidates
1. CTRI direct (search is CAPTCHA-protected; currently via ClinicalTrials.gov cross-registration). SEC rows from committees with non-standard tables (~107 'other').
2. OCR for scanned CDSCO NSQ PDFs (0-row months listed in the feed note).
3. E-pharmacy price refresh beyond DrugSetu, within rate limits. Court-stay tracking for bans.
4. Alerts: email or Telegram notification when an event matches the watchlist or a saved SHELF list.
5. USFDA warning letters and import alerts (fda.gov blocks curl; needs the browser or the FDA data dashboard).

## Gotchas
- **Port 8010.** Another local app (node) uses 8000 on this machine.
- **NPPA compendium** client (`connectors/nppa_dashboard.py`) reproduces the dashboard's AES+RSA request wrapping; needs Origin/Referer headers or the CSRF call returns 'Session Expired'.
- **DuckDB is single-writer.** Stop the server before `build_core`. CLI connector runs delegate to the server when it is up.
- **No DDL inside transactions.** See `derived.migrate()`. `db.get_conn()` applies `schema.sql` (IF NOT EXISTS) on start.
- **Don't edit source through the shell.** Inline `py -c` and heredocs mangle `\b` and apostrophes in this environment, so write patch scripts to files.
- **Stopping the server.** Never kill python by image name. Use `preview_stop` or the server's PID.
