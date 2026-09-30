# WrightWarp

**Airfare Price Index for India: automated collection, cleaning, and index calculation for CPI augmentation**

Prototype for **Smart India Hackathon 2026, Problem Statement 26056**, *"Development of a Real-time
Airfare Price Index for India through Automated Web Scraping of Airline and Online Travel Aggregator
Portals for Augmentation of the Consumer Price Index (CPI)"*. Organization: MoSPI, Data Informatics &
Innovation Division (DIID). Category: Software, Smart Automation.

> ### ⚠ Data status: DEMO
> No real airline or OTA website has cleared compliance review (robots.txt + Terms of Use), and
> WrightWarp does not bypass either. **Every fare shown is SIMULATED** by a statistical market model,
> **route weights are DEMO values (not DGCA data)**, and the **backtest compares against the
> simulator's own ground truth, not official statistics.** All of this is labeled in the API and on
> every dashboard page. The pipeline, index engine, and dashboard are real and source-independent.
> A compliance-cleared source plugs in through the adapter interface without other changes.

- **Live app:** see [Deployment](#deployment) (URL listed there after deploy)
- **API docs:** `/docs` on the deployment · [docs/API.md](docs/API.md)
- **Judge walkthrough:** [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md)

---

## Features

| Area | What exists |
|---|---|
| Collection framework | `SourceAdapter` interface, source registry with compliance gate, per-source rate limiter, bounded retries, per-request checkpoints, structured logs |
| Ethical sources | 11 airline/OTA sources registered, all `PENDING_REVIEW` with documented robots.txt findings; no bypass techniques ([ETHICAL_SCRAPING.md](docs/ETHICAL_SCRAPING.md)) |
| Raw observations | every payload stored first with a SHA-256 hash and provenance |
| Fare normalization | base fare, taxes, airport charges, UDF, fees, total; display-string parsing; missing components never fabricated; IST→UTC timestamps |
| Data quality | 11 rules: required fields, route, dates, lead time, currency, fare bounds, components, sold-out, missing, duplicates, robust-z outliers. One status per observation; nothing deleted |
| Booking windows | T+1/7/15/30/45 (configurable); "fare when bought X days ahead" API |
| Index engine | Jevons elementary aggregates; Laspeyres (headline), Paasche, Fisher, Jevons upper level; route, route × window, booking-window, and overall indices; daily, weekly, monthly |
| Weighting | versioned, validated, checksummed weight sets; OFFICIAL beats DEMO; shipped set is DEMO |
| Provenance | index point → cells → quotes → raw observations → collection runs → source; run-level reproducibility record |
| Backtesting | MAE, RMSE, MAPE, bias, max error, correlation, direction agreement, stability; by methodology, frequency, route, and window; Markdown report |
| Scheduling | daily Vercel Cron: collect every route × window, recompute index; idempotent |
| API | 30+ endpoints, pagination, consistent error model, OpenAPI |
| Dashboard | 9 pages: overview, index, routes, booking windows, sources, quality, backtest, API/methodology, health; responsive; dark mode; chart table views |
| Tests | 220+ pytest tests (unit + MongoDB integration + API) |

## Architecture

```
Sources (registry + compliance gate)
   └─ SourceAdapter ── MOCK (tests) · DEMO_SIM (simulated market) · real adapters: pending review
        └─ raw_observations ─ normalization ─ quality engine ─ flight_quotes
             └─ daily_cells (geo-mean per day × route × window × carrier)
                  └─ index engine: Jevons (route) → Laspeyres / Paasche / Fisher / Jevons (overall, windows)
                       └─ index_series + index_runs ─ backtest_runs
                            └─ FastAPI /api/v1 ─ React dashboard
Deployment: Vercel (CDN dashboard + FastAPI function + Cron) → MongoDB Atlas
```

Details: [ARCHITECTURE.md](docs/ARCHITECTURE.md) · [DATA_PIPELINE.md](docs/DATA_PIPELINE.md) ·
[INDEX_METHODOLOGY.md](docs/INDEX_METHODOLOGY.md) · [BACKTEST_REPORT.md](docs/BACKTEST_REPORT.md) ·
[IMPLEMENTATION_AUDIT.md](docs/IMPLEMENTATION_AUDIT.md)

## Tech stack

Python 3.11+, FastAPI, Pydantic 2, PyMongo (native async), MongoDB Atlas, pytest · React 18, Vite,
TypeScript, React Router, Recharts · Vercel (Python runtime, CDN, Cron) · Playwright (worker-only
abstraction, not deployed).

## Index methodology (summary)

- Price: total payable one-way economy fare in INR, attributed to the IST day it was observed.
- Base: calendar year **2024 = 100**.
- Elementary: route relative = geometric mean of carrier × window relatives vs their base-year
  geometric-mean price.
- Upper level: **Laspeyres** with base-year route expenditure shares (headline). Paasche, Fisher, and
  Jevons are computed alongside.
- Frequencies: daily, ISO-weekly, monthly, all fixed-base.

Full specification: [docs/INDEX_METHODOLOGY.md](docs/INDEX_METHODOLOGY.md).

## Local setup

Prerequisites: Python 3.11+, Node 20+, and either a MongoDB Atlas connection string or Docker
(`docker compose up -d` starts MongoDB 7 locally).

```bash
cp .env.example .env            # set MONGO_URI (Atlas) or leave unset to use local MongoDB

# Backend
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt     # Windows (macOS/Linux: .venv/bin/...)
.venv/Scripts/python.exe -m app.cli seed-demo                    # DEMO history + index + backtest (~3-4 min)
.venv/Scripts/python.exe -m uvicorn app.main:app --reload        # http://127.0.0.1:8000/docs

# Frontend (second terminal)
cd frontend
npm install
npm run dev                                                      # http://localhost:5173 (proxies /api to :8000)
```

`.env` is read from the repo root (or `backend/`) regardless of the working directory.

Other commands (from `backend/`): `python -m app.cli collect-today`, `compute-index`,
`backtest-report`.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `MONGO_URI` | – | full MongoDB connection string (overrides host/port/user/password) |
| `MONGO_DB_NAME` | `wrightwarp` | database |
| `MONGO_HOST`, `MONGO_PORT`, `MONGO_USER`, `MONGO_PASSWORD` | localhost:27017 | local MongoDB (credentials URL-encoded automatically) |
| `ENVIRONMENT` | `development` | `production` on Vercel |
| `CRON_SECRET` | – | bearer secret for `/api/v1/cron/*` and `/api/v1/admin/*`. Without it those endpoints are disabled. |
| `CORS_ORIGINS` | localhost:5173 | comma-separated |
| `DEMO_MODE` | `true` | enables the simulated source and DEMO labeling |
| `INDEX_BASE_YEAR` | `2024` | base period |
| `BOOKING_WINDOWS` | `1,7,15,30,45` | booking windows in days |
| `WEIGHTS_VERSION` | – | pin a weight set version |

## Testing

```bash
cd backend
.venv/Scripts/python.exe -m pytest -q
```

DB-backed tests use the dedicated databases `wrightwarp_test` and `wrightwarp_test_analytics`, whose
collections are dropped after use. The real `wrightwarp` database is never written by tests (only the
app's idempotent startup metadata sync touches it). Frontend: `cd frontend && npm run build` (type
check + production build).

## Deployment

One Vercel project: CDN dashboard, FastAPI function (`index.py`), and daily Cron, backed by MongoDB
Atlas. Steps, environment variables, and verification: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Demo mode

`DEMO_SIM` is a deterministic market simulator: route trends, Indian seasonality (summer, Diwali,
year-end), persistent route and market shocks, a booking-window curve, and carrier price levels.
It deliberately injects sold-out flights, missing totals, component mismatches, duplicates, gross
outliers, total-only payloads, and whole-day gaps, so the quality engine has real work to do.
Everything it produces is `SIMULATED`, and everything derived from it is `DEMO`.

## Limitations

- No real source is cleared, so there is no real or real-time data. The system is fully demonstrable
  on simulated data only.
- The weights are DEMO, not DGCA. The backtest is a recovery test on simulated data, not a validation.
- Items without a base-year price are excluded (no chain-linking of new carriers/routes yet).
- The Vercel Hobby plan runs cron at most daily. Browser-based adapters need a separate worker (not
  deployed).
- Fixed-base index. Monthly values for the current month are month-to-date.

## Future enhancements

1. Complete ToS reviews; pursue official data-sharing/API access with airlines/OTAs through MoSPI.
2. Load DGCA domestic O&D traffic as an `OFFICIAL` weight set.
3. Load the official CPI airfare series into `reference_series` and backtest against it.
4. Chain-linked or rolling-base variants; multilateral (GEKS) methods for high-frequency data.
5. Browser-worker service for approved sources; alerting on collection failures.
6. More routes (tier-2 cities), cabin classes, and a fare-component (tax vs base) sub-index.

## Repository layout

```
backend/app/         FastAPI app (see docs/ARCHITECTURE.md for packages)
backend/tests/       pytest suite
frontend/            React dashboard
docs/                architecture, pipeline, methodology, API, deployment, ethics, demo guide, reports
index.py             Vercel entrypoint · vercel.json · pyproject.toml (runtime deps)
scraper/             notes for a future browser-worker service
docker-compose.yml   local MongoDB
```
