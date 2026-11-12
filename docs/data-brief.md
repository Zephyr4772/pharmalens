# PharmaLens data brief

Live row counts from the production database (srv1), read on 2026-11-12. Fetcher schedules come from the code
(`backend/pharmalens/connectors`). Licence classes are from `licensing.py`; see LICENSING.md before anything leaves
the Tailscale network.

## The numbers

| What | Count | Coverage |
|---|---:|---|
| Catalog SKUs | 543,274 | active and discontinued |
| Molecules / salt combinations | 5,006 / 40,185 | |
| Marketers / corporate groups | 15,680 / 86 | 48 listed on NSE |
| Manufacturers / plant sites | 10,770 / 4,701 | sites placed from approvals, NSQ and FDA records |
| Entity links (record to molecule, maker, site, group) | 904,059 | each with method, confidence, evidence and licence |
| NSQ / spurious batch records | 10,019 | 2019-01 to 2026-09 |
| CDSCO approvals | 4,040 | 2002 to 2026-11 |
| Banned combinations | 690 | |
| Price observations | 657,230 | 2024-06 to 2026-10 |
| Manufacturer price-list rows (Form V and GST sheets) | 18,083 | |
| NPPA retail prices / ceiling prices / ceiling history | 3,585 / 937 / 1,845 | 2019 onward |
| State procurement rates | 7,495 | Rajasthan, Tamil Nadu, Haryana |
| US FDA inspections / Form 483 citations | 39,770 / 38,274 | 2008 to 2026-10 |
| US FDA warning letters and other compliance actions | 2,842 | drug firms worldwide, 210 of them Indian; 2008 to 2026-11 |
| US FDA import refusals (drugs from India) | 11,776 | 2016 to 2026-11 |
| US FDA recalls and import alerts | 649 | 2009 to 2026-11 |
| US applications / Orange Book / NDC / patents | 29,452 / 48,865 / 138,327 / 19,963 | openFDA bulk |
| EMA medicines / WHO prequalified | 2,757 / 657 | |
| India brand registry (Rule 84AB) / CDCI brands | 90,467 / 93,019 | |
| Daily share prices | 245,254 rows | back to 1996 |
| NSE announcements / quarterly results | 41,239 / 1,014 | 2010 onward / FY25 onward |
| News items | 60,922 | 2017 onward |

## The fetchers

49 scheduled jobs: 40 fetch outside data and 9 are internal.

**Indian regulators (13)**

| Fetcher | Source | When |
|---|---|---|
| `cdsco_nsq_portal`, `cdsco_nsq`, `nsq_mirror` | CDSCO NSQ and spurious batches | daily, portal twice |
| `banned_fdc` | CDSCO / MoHFW banned combinations | daily |
| `cdsco_gazette`, `cdsco_alerts` | CDSCO gazette and drug alerts | daily, alerts three times |
| `cdsco_approvals`, `cdsco_approvals_db` | CDSCO approvals | daily, database twice |
| `cdsco_sec` | CDSCO expert committee recommendations | twice daily |
| `cdsco_brands` | Rule 84AB brand registry | weekly |
| `pvpi_alerts` | PvPI drug-safety alerts | weekly |
| `nlem`, `cdci` | NLEM list, CDCI compendium | monthly |

**Prices (6)**

| Fetcher | Source | When |
|---|---|---|
| `nppa_orders`, `nppa_retail_prices` | NPPA orders and retail-price notifications | twice daily |
| `nppa_compendium`, `nppa_history` | NPPA ceiling prices and history | weekly |
| `mfr_price_lists` | manufacturers' Form V price lists | Mon and Thu |
| `jan_aushadhi` | PMBI Jan Aushadhi prices | Mon and Thu |

**State procurement (4)**

| Fetcher | Source | When |
|---|---|---|
| `rmscl_rates` | Rajasthan | Tue and Fri |
| `tnmsc_rates` | Tamil Nadu | Wed and Sat |
| `hmscl_rates` | Haryana | Thursday |
| `upmscl_debarments` | Uttar Pradesh blacklisting | daily, through the laptop relay (the site blocks cloud IPs) |

**Markets (5)**

| Fetcher | Source | When |
|---|---|---|
| `nse_quotes` | NSE prices via Yahoo Finance | every 5 minutes |
| `nse_filings` | NSE announcements | hourly, 09:00 to 18:00 |
| `nse_results` | NSE quarterly results | every 2 hours, 10:00 to 22:00 |
| `nse_fundamentals` | NSE fundamentals | daily |
| `nse_history` | full daily price history | weekly |

**News (2)**

| Fetcher | Source | When |
|---|---|---|
| `pharma_news` | RSS wires | every 15 minutes |
| `news_archive` | GDELT backfill | every 2 hours |

**US and global (10)**

| Fetcher | Source | When |
|---|---|---|
| `fda_inspections`, `fda_compliance` | FDA Data Dashboard: inspections, 483s, warning letters, import refusals | Tuesday |
| `fda_ia_6640` | FDA Import Alert 66-40 | Monday |
| `openfda_recalls` | openFDA recalls | daily |
| `openfda_bulk` | openFDA applications, Orange Book, NDC, patents | Mon and Thu |
| `ctgov_india` | ClinicalTrials.gov, India | daily |
| `who_pq`, `ema_medicines` | WHO prequalification, EMA | Wednesday |
| `who_alerts` | WHO product alerts | daily |
| `molecule_enrichment` | ChEMBL, openFDA labels, FAERS | four times a day |

**Internal jobs (9):** `entity_linker` (daily 05:10), `name_index`, `parent_sync`, `alerts_dispatch` (every 2
minutes), `health_watch` (every 15 minutes), `bot_briefing`, `results_preview`, `results_summary`, `weekly_digest`.

## Health

- Every fetcher's most recent run succeeded (checked 2026-11-12).
- Seven had failed runs in the last 14 days: `cdsco_approvals_db` 23 of 29 runs succeeded, `cdsco_nsq_portal` 26
  of 29, `entity_linker` 25 of 28 (before the memory fix), `upmscl_debarments` 15 of 17 (the laptop relay had not
  run), `fda_inspections` 4 of 6, `tnmsc_rates` 4 of 5 and `cdsco_brands` 2 of 3.
- `health_watch` messages Telegram when a fetcher fails twice, goes stale or the backup stops.

## Licence mix

Of 64 registered tables, 12 are open, 11 need attribution, 5 are gazette text, 12 need permission before sharing
and 24 are our own derived data (about 4.9M rows, mostly catalog links, prices and market shares). The 12
permission tables hold about 353,000 rows (NSQ, approvals, brand registry, sites, procurement). Nothing is public.

## Gaps

- US refusals are placed on a plant only 27% of the time; the rest ship from offices and traders.
- `fin_results` (quarterly results) has no entry in `licensing.py` yet.
- NSQ PDFs from some months are scanned images and load no rows.
- Manufacturer price lists from Ajanta (scanned) and Sanofi (no rows) were still missing at the last check (HANDOFF.md).
- One fetcher (`upmscl_debarments`) depends on the laptop being on at least once every 8 days.
