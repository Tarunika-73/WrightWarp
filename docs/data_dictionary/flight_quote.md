# Data Dictionary — `flight_quotes`

The canonical normalized fare observation. Every current or future
scraper/adapter must normalize its raw output into this shape before
insertion. See `backend/app/models/flight_quote.py` for the ORM
definition and `backend/app/schemas/flight_quote.py` for validation.

| Field | Type | Nullable | Notes |
|---|---|---|---|
| `id` | int | no | Primary key |
| `search_run_id` | int (FK) | no | Links to `search_runs.id` — the audit anchor |
| `source` | string | no | `source_id` from the source registry (`app/core/sources.py`) |
| `airline_id` | int (FK) | yes | Links to `airlines.id` when resolved |
| `airline_code` | string | yes | Raw airline code as seen on the source, kept even if `airline_id` can't be resolved |
| `flight_number` | string | yes | |
| `origin_airport_id` | int (FK) | no | Links to `airports.id` |
| `destination_airport_id` | int (FK) | no | Links to `airports.id`; must differ from origin |
| `departure_datetime` | datetime | yes | |
| `arrival_datetime` | datetime | yes | |
| `travel_date` | date | no | Must not precede `search_datetime` |
| `search_datetime` | datetime | no | When the observation was made |
| `lead_days` | int | no | Must be one of 1, 7, 15, 30, 45 (`app/core/lead_time.py`) |
| `cabin_class` | enum | no | ECONOMY / PREMIUM_ECONOMY / BUSINESS / FIRST |
| `fare_family` | string | yes | |
| `stops` | int | yes | |
| `base_fare` | numeric(12,2) | yes | Nullable — a SOLD_OUT/CANCELLED quote may have none |
| `taxes` | numeric(12,2) | yes | |
| `user_development_fee` | numeric(12,2) | yes | |
| `convenience_fee` | numeric(12,2) | yes | |
| `fuel_surcharge` | numeric(12,2) | yes | |
| `baggage_fee` | numeric(12,2) | yes | |
| `seat_fee` | numeric(12,2) | yes | |
| `meal_fee` | numeric(12,2) | yes | |
| `other_fees` | numeric(12,2) | yes | |
| `total_fare` | numeric(12,2) | yes | Required when `availability_status = AVAILABLE` |
| `currency` | string(3) | no | ISO 4217 code, e.g. `INR` |
| `availability_status` | enum | no | AVAILABLE / SOLD_OUT / CANCELLED / NOT_FOUND / SCRAPE_FAILED / INVALID_QUOTE / UNKNOWN |
| `cancellation_status` | string | yes | Free-text fare-rule detail, distinct from `availability_status` |
| `refundable` | bool | yes | |
| `baggage_included` | bool | yes | |
| `raw_quote_hash` | string(64) | yes | Hash of the raw source payload, used for deduplication |
| `provenance` | enum | no | REAL / SYNTHETIC / SIMULATED — see `docs/architecture/data_model.md` |
| `quality_status` | enum | no | RAW / VALIDATED / REJECTED / OUTLIER / DUPLICATE / PROVISIONAL |
| `quality_score` | numeric(5,4) | yes | 0-1, reserved for future automated scoring |
| `quality_reason` | text | yes | Required when `quality_status = REJECTED` or `availability_status = INVALID_QUOTE` |
| `created_at` | datetime | no | Row insert time |

## Database-level constraints

- `origin_airport_id != destination_airport_id`
- `lead_days IN (1, 7, 15, 30, 45)`
- `base_fare >= 0`, `taxes >= 0`, `total_fare >= 0` (when not NULL)

## Pydantic-level rules (not enforced by Postgres)

- `travel_date` must not precede `search_datetime`
- `AVAILABLE` quotes must carry a `total_fare`
- `REJECTED` / `INVALID_QUOTE` observations must carry a `quality_reason`
- `currency` must be a 3-character code
