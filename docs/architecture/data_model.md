# WrightWarp Phase 1 — Data Model & Design Decisions

## Audit chain

Every fare observation must be traceable end-to-end:

```
source (config registry)
  -> search_run (one collection attempt)
    -> flight_quote (normalized observation, search_run_id FK)
      -> quality_status / quality_reason (pipeline decision, recorded on the quote itself)
        -> [Phase 2+] index_cell
          -> [Phase 2+] final index
```

`search_runs` is the anchor: it records what was searched (source, route,
travel date, lead-time window), when, and how many raw/valid records came
back, independent of whether any usable `flight_quotes` rows were
produced (a `SCRAPE_FAILED` run still leaves a row with `error_message`
set). Every `flight_quotes` row carries `search_run_id`, so any fare in
the system can be traced back to the exact collection attempt, source,
and request parameters that produced it.

## Provenance vs. quality — why they are separate fields

`FlightQuote` carries two independent controlled-vocabulary fields
instead of one combined status:

- **`provenance`** (`REAL` / `SYNTHETIC` / `SIMULATED`) — where the
  observation *came from*. `REAL` means it was actually collected from a
  live airline/OTA source. `SYNTHETIC` means it was fabricated (e.g. to
  exercise the pipeline or write deterministic tests). `SIMULATED` is
  reserved for model/heuristic-generated stand-ins for a source that is
  not yet connected. This value is set once, at ingestion, and never
  changes.
- **`quality_status`** (`RAW` / `VALIDATED` / `REJECTED` / `OUTLIER` /
  `DUPLICATE` / `PROVISIONAL`) — what the data-quality pipeline has
  *decided* about the observation. This changes as the pipeline runs
  (e.g. `RAW` -> `VALIDATED`, or `RAW` -> `OUTLIER`).

Collapsing these into a single enum would make it impossible to express
real combinations that the project explicitly needs to represent, e.g. a
`REAL` observation that has not yet been validated (`REAL` + `RAW`), or a
`SYNTHETIC` fixture that is deliberately marked `VALIDATED` to test
downstream code. Keeping the axes orthogonal is also what makes it
possible to honestly answer "is this REAL data or a placeholder?"
independently of "has this been through quality control?" — which is a
hard requirement from the problem statement (never present synthetic
data as if it were collected real-world data).

`quality_reason` is a free-text field that must be populated whenever a
quote is `REJECTED` or has `availability_status = INVALID_QUOTE`, so a
rejection is never silent.

## Availability vs. cancellation

`availability_status` is the primary controlled vocabulary for "what
happened when we tried to price this itinerary" (`AVAILABLE`,
`SOLD_OUT`, `CANCELLED`, `NOT_FOUND`, `SCRAPE_FAILED`, `INVALID_QUOTE`,
`UNKNOWN`). `cancellation_status` is a separate, currently free-text
field reserved for finer-grained cancellation/refund-policy detail
(e.g. a specific fare rule code) that a source may expose later — it is
not a duplicate of `CANCELLED` in `availability_status`.

## Nullable fare fields

All fare-breakdown columns (`base_fare`, `taxes`, ... `total_fare`) are
nullable. A `SOLD_OUT` or `CANCELLED` quote legitimately carries no
price; forcing a zero or fabricated value there would corrupt any
downstream index calculation. The validation rule instead requires that
`AVAILABLE` quotes always carry a `total_fare` (enforced both at the
Pydantic layer and the calling code is expected to keep this invariant
before insert).

## Routes and weights

`routes.weight` is nullable and defaults to `NULL`. No DGCA/MoSPI market
share weighting data has been supplied as of Phase 1, so no placeholder
numeric weight is invented. Anything downstream that reads `weight` must
treat `NULL` as "not yet weighted," never as zero.

## Sources are configuration, not a database table

`app/core/sources.py` defines the source registry (airline codes, OTA
placeholders, and the ethical-scraping flags each future adapter must
declare) as static Python configuration rather than a database table.
Phase 1 implements no scraper, so there is no runtime state (rate-limit
counters, last-run timestamps, etc.) that would justify a table yet;
`search_runs.source` references a `source_id` from this registry by
convention (not a DB foreign key, since the registry is not a table).
