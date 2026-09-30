# Implementation Audit (pre-Phase 3)

Audit of the repository as found at commit `ec1f33a` ("Initial commit"),
before any Phase 3 work. Written so the starting point of the Phase 3
changes is on record.

## 1. Current architecture

```
backend/app/
  main.py                FastAPI app, lifespan: connect Mongo -> ensure indexes -> sync source registry
  core/                  config (pydantic-settings), enums, lead-time windows, source registry, validators
  db/                    AsyncMongoClient lifecycle, index bootstrap, BSON/ObjectId helpers
  models/                Mongo document shapes (Pydantic): airlines, airports, routes, search_runs,
                         raw_observations, flight_quotes (nested), collection_errors, sources
  schemas/               API/pipeline contracts: CollectionRequest/Result, FlightQuoteCreate/Read, RouteBase
  repositories/          one repository per collection (the only code that touches PyMongo)
  collection/            SourceAdapter ABC, MockSourceAdapter, AdapterRegistry, RateLimiter,
                         normalizer, CollectionRepository, CollectionService, Playwright browser abstraction
  api/                   /health, /health/db, /api/v1/sources, /api/v1/collections[/{id}]
backend/tests/           pytest suite
docs/architecture, docs/methodology, docs/data_dictionary
scraper/, index_engine/, dashboard/, data/   empty placeholders (.gitkeep only)
docker-compose.yml       local MongoDB 7
```

Database: **MongoDB** (PyMongo native async API). The `.env` at the repo
root points `MONGO_URI` at a **MongoDB Atlas** cluster
(`mongodb+srv://…wrightwarp-cluster…`); `docker-compose.yml` provides a
local alternative. Atlas was reachable during the audit; the `wrightwarp`
database contained only the 12 synced `sources` documents.

## 2. Implemented functionality

- Source registry with compliance metadata. All 11 real airline/OTA
  sources are `PENDING_REVIEW` and disabled; robots.txt findings are
  documented in `docs/architecture/source-adapters.md`. Only `MOCK` is
  `IMPLEMENTED`.
- `CollectionService`: compliance gate, per-source async rate limiter,
  bounded retries for transient errors only, raw observation persistence
  with payload hash, normalization to the canonical `FlightQuoteCreate`,
  per-request checkpointing via `search_runs`, structured logs, durable
  `collection_errors`.
- `MockSourceAdapter`: deterministic synthetic fare, tagged `SYNTHETIC`.
- Canonical fare schema already has slots for base fare, taxes, UDF,
  convenience fee, fuel surcharge, ancillaries, total fare.
- Lead-time windows T+1/7/15/30/45 centralised in `app/core/lead_time.py`.
- Separate provenance (`REAL/SYNTHETIC/SIMULATED`) and quality
  (`RAW/VALIDATED/REJECTED/OUTLIER/DUPLICATE/PROVISIONAL`) axes.

## 3. Incomplete functionality (not started)

- Data-quality engine (dedup, outliers, missing values, component checks).
- Index engine, weighting, daily/weekly/monthly aggregation, backtesting.
- Route master data and route/fare/index APIs.
- Scheduled collection.
- Frontend dashboard.
- Deployment configuration (no Vercel or Render config exists in the
  repository; no CI).

## 4. Broken functionality

Test run at audit time: **81 passed, 2 failed, 17 errors**.

| Problem | Root cause |
|---|---|
| All DB-backed tests fail when run from `backend/` (as the README instructs) | `Settings` uses `env_file=".env"`, resolved relative to the working directory. The only `.env` is at the repo root, so from `backend/` the Atlas URI is ignored and the app falls back to `localhost:27017`, where nothing is running. |
| `test_health_db_endpoint`, `test_collection_api.*` | The module-level `AsyncMongoClient` is created on one event loop (a `TestClient` lifespan) and later reused on another. PyMongo's async client is bound to the loop it was created on. The same failure mode would occur on any serverless runtime that recreates the event loop. |
| `test_collection_e2e.py`, `test_collection_persistence.py` do not import | Left over from the PostgreSQL/SQLAlchemy era (`FlightQuote`, `db_session`, `seed_airports` no longer exist). |
| README | Still describes PostgreSQL, SQLAlchemy, and Alembic, none of which the code uses. |

## 5. Technical risks

- Raw payload hash is computed, but `FlightQuote.raw_quote_hash` is never
  set, so quote-level duplicate detection has nothing to key on.
- The normalizer requires a `CollectionRequest`, whose validator rejects
  past travel dates. Historical/backfill data therefore cannot pass
  through it.
- `CollectionService` infers provenance from `source_id == "MOCK"`, so a
  second synthetic source would be mislabeled `REAL`.
- Playwright is a hard runtime dependency (~100 MB of browsers when
  installed) even though no adapter uses it.

## 6. Deployment risks

- Serverless (Vercel) functions may not run the ASGI lifespan and can
  recreate event loops, so the Mongo client needs lazy, loop-aware
  initialisation.
- Atlas network access must allow the deployment's egress IPs (Vercel has
  no static egress IPs on Hobby, so `0.0.0.0/0` plus strong credentials
  is the practical setting).
- Browser-based collection cannot run in a Vercel function. Any real
  Playwright adapter needs a separate worker.
- Vercel Hobby cron runs at most once per day.

## 7. Recommended implementation sequence

1. Fix `.env` resolution and the loop-aware Mongo client; repair the stale tests.
2. Build a quality engine as pure functions and wire it into `CollectionService`.
3. Refactor normalization so it no longer depends on `CollectionRequest`, preserving components and never fabricating them.
4. Add route master data and a simulated demo market with its own source and `SIMULATED` provenance.
5. Build elementary aggregates (daily cells), then the index engine (Jevons / Laspeyres / Paasche / Fisher), weighting, and D/W/M series.
6. Add backtesting against the simulator's ground truth, labeled DEMO.
7. Add APIs, global error handling, and a cron endpoint.
8. Build the React dashboard.
9. Write docs, then deploy to Vercel (preview, then production).
