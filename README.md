# WrightWarp

**Real-Time Airfare Price Intelligence & Indexing Platform for India**

Prototype for Smart India Hackathon problem statement **SIH26056**. This
repository is being built phase by phase. **Phase 1 (foundation) and
Phase 2 (data collection framework) are complete; nothing beyond that
exists yet.**

---

## 1. Problem

Indian domestic airfares are volatile and opaque to consumers, analysts,
and policymakers. SIH26056 asks for an automated system that collects
airfare data from airline and OTA sources, cleans and normalizes it, and
produces a statistically defensible Airfare Price Index — validated
against official reference data — exposed via a dashboard and API.

## 2. Objectives

- Ethical, rate-limited, robots.txt/ToS-respecting collection from
  airline and OTA sources, across multiple routes and advance-purchase
  windows (T+1, T+7, T+15, T+30, T+45).
- Rigorous data cleaning: deduplication, outlier handling, missing-value
  and sold-out/cancellation handling.
- A defensible index (Laspeyres / Paasche / Fisher / Jevons) with
  official-data backtesting.
- An interactive dashboard and a public API for statistical consumers.
- Total honesty about data provenance: REAL vs SYNTHETIC vs SIMULATED vs
  PROVISIONAL vs VALIDATED data is never conflated.

## 3. Architecture (target — Phase 3/4 stages are NOT IMPLEMENTED YET)

```
                AIRLINE / OTA SOURCES
                          |
                          v
                SOURCE ADAPTER LAYER            <- Phase 2: interface + MockSourceAdapter only;
                          |                         every real source PENDING_REVIEW (not scraped)
                          v
                RAW OBSERVATION STORAGE          <- Phase 2: raw_observations table (JSONB)
                          |
                          v
                DATA QUALITY PIPELINE            <- NOT IMPLEMENTED YET (Phase 3)
                          |
                          v
                NORMALIZED QUOTES                 <- Phase 2: MockSourceAdapter -> Normalizer -> flight_quotes
                          |
         +----------------+----------------+
         |                |                |
         v                v                v
     LASPEYRES         JEVONS          FISHER      <- NOT IMPLEMENTED YET (Phase 3)
         |                |                |
         +----------------+----------------+
                          |
                          v
                 WRIGHTWARP INDEX                  <- NOT IMPLEMENTED YET (Phase 3)
                          |
         +----------------+----------------+
         |                |                |
         v                v                v
    DASHBOARD           API          STATISTICAL EXPORT   <- NOT IMPLEMENTED YET (Phase 4)
                    (/health, /api/v1/sources, /api/v1/collections exist
                     as development endpoints — not the statistical API)
```

The system is designed so the scraper, quality pipeline, and index
engine are separate modules connected only through the database schema —
any one of them can be rebuilt without rewriting the others.

## 4. Technology stack

**Backend (in place):** Python 3.11+, FastAPI, SQLAlchemy 2.x,
Pydantic 2.x, Alembic, PostgreSQL, pytest, pytest-asyncio.

**Collection framework (Phase 2, in place):** Playwright (dependency +
lightweight `BrowserManager`/`SessionManager`/`PageManager` abstraction;
not wired into any adapter yet — no real source has cleared compliance
review). Real scraping of any specific site — Scrapy,
BeautifulSoup/lxml, or otherwise — is NOT IMPLEMENTED YET.

**Future analytics:** Pandas, NumPy, SciPy, Statsmodels — NOT
IMPLEMENTED YET.

**Future frontend:** React, Vite, Tailwind CSS, Recharts — NOT
IMPLEMENTED YET.

**Infrastructure:** Docker / Docker Compose (PostgreSQL only, in place).
GitHub Actions — NOT IMPLEMENTED YET.

## 5. Phase 1 status

Implemented:

- Repository structure for all planned modules (backend, scraper,
  index_engine, dashboard, docs, data), with future directories left
  empty (`.gitkeep` only) rather than pre-populated with fake code.
- FastAPI application (`backend/app/main.py`) with `GET /health` and
  `GET /health/db`.
- SQLAlchemy 2.x models for `airlines`, `airports`, `routes`,
  `search_runs`, and the canonical `flight_quotes` table.
- Alembic configured and an initial migration generated and applied.
- PostgreSQL running via Docker Compose with a persistent named volume.
- Lead-time window configuration (T+1/7/15/30/45) as importable config,
  not scattered literals.
- Source registry (airlines + OTA placeholders) with ethical-scraping
  flags, as static configuration — no scraper exists to use it yet.
- Controlled vocabularies for availability status, data quality status,
  and data provenance (kept as separate axes — see
  `docs/architecture/data_model.md`).
- Pydantic validation rules (see §9 below).
- 44 automated tests, all passing.

Explicitly NOT implemented in Phase 1:

- No scraping of any kind.
- No dashboard.
- No index calculation.
- No backtesting.

## 5a. Phase 2 status

Implemented:

- Source-independent collection contracts (`app/schemas/collection.py`):
  `CollectionRequest`, `CollectionResult`, `CollectionOutcome`,
  `CollectionError`.
- `SourceAdapter` interface (`app/collection/adapters/base.py`) — small,
  no persistence logic — and `MockSourceAdapter`, the only implemented
  adapter, returning deterministic, clearly `SYNTHETIC` observations.
- Source registry extended with compliance metadata and a `SourceStatus`
  (`CONFIGURED`/`IMPLEMENTED`/`DISABLED`/`PENDING_REVIEW`) — every real
  airline/OTA is `PENDING_REVIEW`; only `MOCK` is `IMPLEMENTED`. See
  `docs/architecture/source-adapters.md` for the actual robots.txt
  findings behind that decision.
- `RawObservation` model + migration (JSONB payload, hash, provenance,
  status) — the auditable link between what an adapter saw and the
  `FlightQuote` rows derived from it.
- `CollectionService`: compliance check -> async `RateLimiter` -> adapter
  (with bounded, conservative retries) -> normalize -> persist, all
  wired to the existing `search_runs`/`flight_quotes` tables.
- Checkpointing via `SearchRun.status` (extended with `RETRY`,
  `SKIPPED`, `BLOCKED`, `NO_RESULTS`) — one row per request, so a batch
  of requests never loses a completed request's status when another
  fails.
- Structured logging (`collection_started`/`completed`/`failed`/
  `blocked`, with source/route/lead-time/duration/record counts; no
  secrets).
- Playwright added as a dependency with a minimal, unused-by-default
  `BrowserManager`/`SessionManager`/`PageManager` abstraction — no
  stealth/CAPTCHA logic, nothing launches automatically.
- Development API endpoints: `GET /api/v1/sources`,
  `POST /api/v1/collections`, `GET /api/v1/collections/{id}` — no
  arbitrary-URL scraping endpoint exists or ever will.
- 99 automated tests, all passing (55 new in Phase 2).

Explicitly NOT implemented in Phase 2 (see §11):

- No real source adapter (every airline/OTA is `PENDING_REVIEW`).
- No data-quality pipeline (dedup/outlier/missing-value handling).
- No index calculation, dashboard, or backtesting.

## 6. Database design

| Table | Purpose |
|---|---|
| `airlines` | Reference list of Indian carriers (code, name, active) |
| `airports` | Reference list of airports (IATA code, city, state) |
| `routes` | Monitored origin-destination pairs; `weight` is `NULL` until an official DGCA/MoSPI figure is supplied |
| `search_runs` | One row per collection attempt — source, route, travel date, lead window, status, record counts, error message. Also the Phase 2 checkpoint unit. |
| `raw_observations` | *(Phase 2)* One row per raw payload an adapter captured, before normalization — JSONB payload, payload hash, provenance, status. FK to `search_runs`. |
| `flight_quotes` | Canonical normalized fare observation — see `docs/data_dictionary/flight_quote.md` |

Full field-by-field documentation: `docs/data_dictionary/flight_quote.md`.
Design rationale (provenance vs. quality, nullable fares, route
weights): `docs/architecture/data_model.md`. Phase 2 collection
architecture: `docs/architecture/data-collection.md`,
`docs/architecture/source-adapters.md`, `docs/architecture/data-flow.md`.

## 7. Data provenance

Every quote is designed to be traceable: `source` (registry) ->
`search_run` (collection attempt) -> `raw_observation` (Phase 2; the
exact raw payload captured) -> `flight_quote` (normalized observation,
carrying `provenance` and `quality_status`) -> [Phase 3+] index cell ->
[Phase 3+] final index. See `docs/architecture/data_model.md` and
`docs/architecture/data-collection.md` for the full chain and why
`provenance` and `quality_status` are kept as separate fields.

**No real airfare data has been collected. Every value used in tests or
examples in this repository is explicitly `SYNTHETIC`**, produced only by
`MockSourceAdapter` and always tagged as such end-to-end.

## 8. Ethical scraping principles

No real-source scraper exists yet — every airline/OTA in the registry is
`PENDING_REVIEW` (see `docs/architecture/source-adapters.md` for the
actual robots.txt findings: ixigo, Cleartrip, EaseMyTrip, and SpiceJet's
API path were all found to explicitly disallow automated fare-search
access; IndiGo, Air India, MakeMyTrip, and Akasa's Terms of Use could not
be reviewed in this pass and remain unreviewed rather than assumed
permitted). `CollectionService` enforces this in code — it refuses to
dispatch to any source that is not both `SourceStatus.IMPLEMENTED` and
`enabled` (`app/core/sources.py`), returning `COMPLIANCE_BLOCKED` instead.
This project will never implement CAPTCHA bypass, anti-bot stealth
techniques, unauthorized proxy/IP rotation, authentication bypass, or
rate-limit bypass. A future real adapter must respect robots.txt, that
source's Terms of Service, a conservative per-source rate limit
(`RateLimiter`, `app/collection/rate_limiter.py`), and any documented
session rules — and must pass the same documented review before its
status can change.

## 9. Planned index methodology

NOT IMPLEMENTED YET. See `docs/methodology/index_methodology.md` for the
current (non-binding) direction: Laspeyres/Paasche/Fisher/Jevons
computed side by side, DGCA-sourced route weights only, and no index
value described as "validated" without 30+ days of backtesting against
public reference data.

## 10. Testing

99 pytest tests in `backend/tests/`. Phase 1 (44): the health endpoint,
live database connectivity, that all Phase 1 tables exist, lead-time
configuration, the availability/provenance/quality enums, route-code
validation, and FlightQuote validation (negative fares, mismatched
origin/destination, unsupported lead-time windows, travel date before
search date, AVAILABLE-without-fare, REJECTED/INVALID-without-reason).

Phase 2 (55): `CollectionRequest` validation, the source registry
(lookup, unknown source, every real source `PENDING_REVIEW`),
`MockSourceAdapter` (deterministic, synthetic provenance),
`CollectionService` (success, retry-then-success, failure after
exhausting retries, non-retryable errors, no-results, compliance-blocked,
disabled-source), the async `RateLimiter`, `SearchRun`/`RawObservation`/
`FlightQuote` persistence and relationships, the `/api/v1/sources` and
`/api/v1/collections` endpoints, and one full end-to-end synthetic-quote
pipeline test.

Collection-framework tests that write to the database run inside a
SQLAlchemy SAVEPOINT per test (`backend/tests/conftest.py::db_session`)
so nothing they persist ever reaches the real database, even though the
framework code itself calls `session.commit()`.

Run with:

```bash
cd backend
.venv/Scripts/python.exe -m pytest -q      # Windows
# or: .venv/bin/python -m pytest -q         # macOS/Linux
```

All 99 currently pass against a live PostgreSQL instance (started via
`docker compose up -d` from the repo root).

## 11. Roadmap

- **Phase 1:** foundation — repo structure, schema, migrations, health
  checks, config, tests. Complete.
- **Phase 2:** source-independent collection framework — contracts,
  `SourceAdapter` interface, source registry + compliance metadata,
  rate limiter, browser abstraction, `MockSourceAdapter`,
  `CollectionService`, checkpointing, retries, structured logging,
  development API endpoints, end-to-end synthetic test. Complete. No
  real source adapter exists — every one is `PENDING_REVIEW`.
- **Phase 3 (not started):** data-quality pipeline (dedup, outlier,
  missing-value/sold-out handling) and the index engine (Laspeyres/
  Paasche/Fisher/Jevons), daily/weekly/monthly aggregation, DGCA
  backtesting.
- **Phase 4 (not started):** dashboard, statistical-consumer API,
  documentation site.

**Do not begin Phase 3 without an explicit request.**

## 12. Development setup

### Prerequisites

- Python 3.11+
- Docker Desktop (for PostgreSQL)

### Steps

```bash
# 1. From the repo root: copy env config
cp .env.example .env

# 2. Start PostgreSQL
docker compose up -d

# 3. Set up the backend
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# or: .venv/bin/pip install -r requirements.txt                # macOS/Linux

# 4. Apply migrations
.venv/Scripts/python.exe -m alembic upgrade head

# 5. Run the API
.venv/Scripts/python.exe -m uvicorn app.main:app --reload

# 6. Verify
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/db
curl http://127.0.0.1:8000/api/v1/sources

# 7. Run tests
.venv/Scripts/python.exe -m pytest -q
```

### Trying the collection framework manually

`POST /api/v1/collections` needs at least one `airports` row for the
origin and destination IATA codes you use (Phase 1 ships no seed data).
For example, to insert `DEL`/`BOM` and then run a synthetic collection:

```bash
cd backend
.venv/Scripts/python.exe -c "
from app.db.session import SessionLocal
from app.models.airport import Airport
db = SessionLocal()
db.add(Airport(iata_code='DEL', name='Indira Gandhi International', city='Delhi'))
db.add(Airport(iata_code='BOM', name='Chhatrapati Shivaji Maharaj International', city='Mumbai'))
db.commit()
"

curl -X POST http://127.0.0.1:8000/api/v1/collections \
  -H "Content-Type: application/json" \
  -d '{"source_id":"MOCK","origin":"DEL","destination":"BOM","travel_date":"2026-12-01","lead_days":15}'

# GET /api/v1/collections/{search_run_id} (id from the response above) returns its checkpoint status.
```

A request with `source_id` set to any real airline/OTA (e.g. `"6E"`)
returns `"outcome": "BLOCKED"` — every real source is `PENDING_REVIEW`
(see `docs/architecture/source-adapters.md`).
