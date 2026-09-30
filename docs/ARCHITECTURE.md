# Architecture

## Deployment topology

```
                 ┌───────────────────────────── Vercel project ─────────────────────────────┐
 Browser ──────> │  CDN: React dashboard (frontend/dist, /assets/*)                          │
                 │  Function: FastAPI (index.py -> backend/app/main.py)                      │
                 │      /health, /docs, /api/v1/*                                            │
 Vercel Cron ──> │      GET /api/v1/cron/daily  (Bearer CRON_SECRET, 00:30 UTC)              │
                 └──────────────────────────────────┬────────────────────────────────────────┘
                                                    │ TLS (mongodb+srv)
                                                    v
                                     MongoDB Atlas  (database: wrightwarp)
```

- **One Vercel project** serves both the dashboard and the API from one origin, so production needs
  no CORS and no API URL configuration. Vercel's FastAPI runtime detects `index.py`, and the build
  command compiles the Vite app. `app.mount("/assets")` is promoted to the CDN
  (`[tool.vercel.fastapi.static] cdn = true`), and other SPA paths fall back to `index.html` in the
  function.
- **MongoDB Atlas** holds all state. The Mongo client is created lazily and is event-loop aware,
  because a serverless invocation may not share the loop that created an earlier client.
- **Vercel Cron** triggers the daily collection and index recomputation. The demo source makes no
  network calls, so a full pass fits well within a single invocation (300 s limit).
- **Worker architecture (not deployed).** A real, browser-based source cannot run inside a Vercel
  function: there are no browser binaries, and time and bundle limits apply. It would run as a
  separate worker (a container on any job runner) that uses the same `CollectionService` and writes
  to the same Atlas database. After a run, the worker calls `POST /api/v1/admin/recompute-index`.
  Playwright is therefore a worker-only dependency (`backend/requirements.txt`) and is not part of
  the deployed function (`pyproject.toml`).

## Backend layers (`backend/app`)

| Package | Responsibility |
|---|---|
| `core/` | settings, enums, booking windows, route master data, source registry, error types |
| `db/` | Mongo client lifecycle, index bootstrap |
| `models/`, `schemas/` | Mongo document shapes; API and pipeline contracts |
| `repositories/` | the only code that talks to PyMongo collections |
| `collection/` | `SourceAdapter` interface, adapters (`mock`, `simulated`), rate limiter, `CollectionService`, Playwright abstraction |
| `normalization/` | fare-component normalization; the shared `process_observation` pipeline |
| `quality/` | quality rules (pure) and the Mongo-backed context builder |
| `index_engine/` | periods, weights, calculators, engine (pure), backtest (pure), service (Mongo), report |
| `demo/` | market simulator and historical backfill (DEMO only) |
| `scheduling/` | daily collection job |
| `api/` | FastAPI routers |
| `cli.py` | `seed-demo`, `collect-today`, `compute-index`, `backtest-report` |

Pure modules (normalization, quality rules, calculators, engine, backtest) have no database access,
so every number they produce can be unit-tested and reproduced from its inputs.

## MongoDB collections

| Collection | Content |
|---|---|
| `sources` | read mirror of the source registry |
| `airports`, `routes` | read mirror of route master data |
| `search_runs` | one per collection attempt (checkpoint) |
| `raw_observations` | raw parsed payload, SHA-256 hash, provenance, quality decision |
| `flight_quotes` | canonical normalized quote (nested: route, travel, flight, fare, quality, provenance) plus `dedup_key` |
| `collection_errors` | structured collection errors |
| `daily_cells` | elementary aggregates (day × route × window × carrier) |
| `index_series` | computed series, one document per methodology × frequency × scope, tagged with `run_id` |
| `index_runs` | reproducibility record per computation |
| `index_meta` | pointer to the current run |
| `backtest_runs` | backtest reports |
| `scheduled_jobs` | scheduled job summaries |
| `reference_series` | optional official reference series for backtesting (none shipped) |

## Frontend (`frontend/`)

React 18, Vite, TypeScript, React Router, and Recharts. Pages: Overview, Airfare Index, Route
Analysis, Booking Windows, Source Monitoring, Data Quality, Backtesting, API & Methodology, and
System Health. Every chart has a legend (for two or more series), a crosshair tooltip, and a table
view. Colours come from a CVD-validated palette with a separate dark-mode set. A DEMO banner is
shown whenever `/api/v1/meta` reports demo mode.

## Security

- Secrets (`MONGO_URI`, `CRON_SECRET`) come from environment variables only. `.env` is git- and
  vercel-ignored. The Mongo URI is never logged, and database errors are logged by exception class
  only.
- Scheduled and admin endpoints require `Authorization: Bearer $CRON_SECRET` (constant-time
  compare). Without a configured secret they refuse every request.
- A global exception handler returns a generic 500 with a request id. Stack traces never reach
  clients.
- CORS is limited to the configured origins and the `GET`/`POST` methods.
- The public API is read-only except `POST /api/v1/collections`, which accepts only registered,
  compliance-cleared sources.
