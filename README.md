# PharmaLens — India Pharma Terminal

A real-time intelligence terminal for the Indian pharmaceutical market, built for doctors,
NGOs and procurement teams, pharma companies sizing up the market, and analysts. It is not
a consumer app and does no symptom or disease prediction.

| Screen | Key | What it answers |
|---|---|---|
| MKT | 1 | What changed today: bans, NSQ batches, recalls, price notices, stock moves, news, segment structure |
| REG | 2 | Government desk: CDSCO NSQ/spurious batch ledger, prohibited FDCs and the catalog SKUs they hit, gazette/circulars/NPPA orders, USFDA recalls, Jan Aushadhi, NPPA ceilings, shortages |
| SHELF | 3 | Paste or upload an inventory CSV; flags banned FDCs, NSQ/spurious batch numbers, expiry, discontinued, maker quality history, cheaper same-form brands, Jan Aushadhi price |
| SCRN | 4 | Product screener (class, form, single/FDC, MRP, ban/stock status) with CSV export |
| MOL | 5 | Molecules: brands, marketers, combinations, concentration (HHI), NPPA ceiling, NSQ history, bans |
| FDC | 6 | Salt combinations (molecules + strengths + dosage form): per-unit price spreads, brand ladders, who owns each |
| CO | 7 | Corporate groups (subsidiaries rolled up) and all 15k marketers: portfolio, segment share, category leadership, quality record |
| EQ | 8 | Listed pharma equities (NSE) with market cap, 52-week range, sparklines |
| NEWS | 9 | News wire classified by topic and tagged to groups |
| FEED | 0 | Connector health, run-now, sources and methodology |
| WATCH | W | Starred SKUs/molecules/combinations/companies and events about them |
| PIPE | P | CDSCO new drug approvals, SEC recommendations, clinical trials in India |
| ALERT | A | Alert subscriptions (watchlist / shelf list) to Telegram, email, webhooks; inbox and daily digest |

## Run

```bash
py -3 -m pip install -r backend/requirements.txt
```
```bash
cd web && npm install && npm run build
```
```bash
cd backend && py -3 -m pharmalens.pipeline.build_core
```
```bash
cd backend && py -3 -m uvicorn pharmalens.api.main:app --port 8010
```

Open http://localhost:8010. The server runs the connector scheduler in-process (set
`PHARMALENS_SCHEDULER=0` to disable). Run a connector by hand with
`py -3 -m pharmalens.connectors run <name>` (it goes through the server if one is running).

Put secrets in `.env` (see `.env.example`): optional `OPENFDA_API_KEY`, and for alerts `TELEGRAM_BOT_TOKEN` and/or `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`.

## Data

Source datasets live in `data/sources/` (not in git):
- `kaggle/indian-medicine-master-dataset` — the catalog spine
- `kaggle/india-medicines-and-drug-info-dataset` — 2025 1mg prices and stock
- `legacy/` — the 2024 project JSON

Download the Kaggle sets with `kaggle datasets download -d <slug> -p data/sources/kaggle/<slug> --unzip`.

See [docs/METHODOLOGY.md](docs/METHODOLOGY.md) for sources, refresh cadence, market-share estimation and matching rules.
