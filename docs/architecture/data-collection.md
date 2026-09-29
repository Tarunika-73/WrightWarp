# WrightWarp Phase 2 — Data Collection Framework

This document describes the source-independent collection framework
added in Phase 2. It does not describe any specific source's scraper
(there isn't one yet - see `source-adapters.md`), only the pipeline every
future source will plug into.

## Pipeline

```
CollectionRequest
      |
      v
CollectionService            (validation, compliance, rate limiting, retries)
      |
      v
SourceAdapter                (one per source; only MockSourceAdapter exists)
      |
      v
AdapterSearchOutcome         (raw findings, in memory)
      |
      v
RawObservation                (persisted, PostgreSQL)
      |
      v
Normalizer
      |
      v
FlightQuote                   (persisted, PostgreSQL)
```

Every request produces exactly one `SearchRun` row (`backend/app/models/
search_run.py`, already part of Phase 1) - this is the audit anchor and
the checkpoint unit: a batch of requests (e.g. one route across every
T+ lead-time window) is just several independent `SearchRun`s, so one
failing never affects the recorded status of the others
(`CollectionService.run_batch`).

## Why the pipeline is split into these stages

| Stage | Lives in | Knows about |
|---|---|---|
| `SourceAdapter` | `app/collection/adapters/*` | How to reach *one* source and return raw findings. Nothing about the database. |
| Normalizer | `app/collection/normalizer.py` | How to turn one raw payload into a canonical `FlightQuoteCreate`. Nothing about a specific source's HTML/JSON shape beyond what the adapter already extracted. |
| Repository | `app/collection/repository.py` | How to persist `SearchRun`/`RawObservation`/`FlightQuote` rows. Nothing about compliance, retries, or rate limits. |
| `CollectionService` | `app/collection/service.py` | How to orchestrate the above: compliance check -> rate limiter -> adapter (with retries) -> persist raw -> normalize -> persist quote. No statistics, no index logic. |

This separation is what lets Phase 2 add a second, third, or tenth
source by writing one new adapter class - nothing above the adapter
layer needs to change.

## Contracts (`app/schemas/collection.py`)

- **`CollectionRequest`** - `source_id`, `origin`/`destination` (IATA
  codes, not internal airport IDs - a request should look like what
  you'd type into a source's own search form), `travel_date`, `lead_days`,
  `passenger_count`, `cabin_class`. Validates `origin != destination`,
  `lead_days` against the existing `app.core.lead_time` configuration
  (reused, not re-implemented), `passenger_count >= 1`, and
  `travel_date` not in the past.
- **`CollectionResult`** - `success`, `outcome` (see below), `source`,
  the original `request`, `started_at`/`completed_at`,
  `records_found`/`raw_observations_persisted`/`quotes_normalized`,
  and `errors`/`warnings`.
- **`CollectionOutcome`** (`app/core/enums.py`) - `SUCCESS`, `PARTIAL`,
  `FAILED`, `BLOCKED`, `NO_RESULTS`. A `FAILED` or `BLOCKED` attempt is
  never reported as "0 flights found" - `NO_RESULTS` is a distinct,
  legitimate outcome (the search ran fine and genuinely found nothing).
- **`CollectionError`** - `error_type` (`CollectionErrorType`),
  `message`, optional `detail`, `retryable`. Never carries a traceback,
  headers, cookies, or other session detail.

## Retry policy

Only `NETWORK_ERROR`, `TIMEOUT`, `SOURCE_UNAVAILABLE`, and `RATE_LIMITED`
are retried (`app/collection/errors.py::RETRYABLE_ERROR_TYPES`), with
exponential backoff (`backoff_seconds * 2**(attempt-1)`) and a bounded
`max_attempts` (default 3). `VALIDATION`/`INVALID_REQUEST`,
`COMPLIANCE_BLOCKED`, `AUTH_ERROR`, and `PARSER_ERROR` are never retried
- retrying a request a source's robots.txt/ToS disallows, or one that
was malformed, would never succeed and is not "responsible collection".
A retry that eventually succeeds is recorded in `CollectionResult.
warnings`, not `errors`, so a recovered transient hiccup never taints an
otherwise-successful result as `PARTIAL`.

## Checkpointing

There is no separate "checkpoint" table: `SearchRun.status`
(`app/core/enums.py::SearchRunStatus`, extended in Phase 2 with
`RETRY`, `SKIPPED`, `BLOCKED`, `NO_RESULTS`) *is* the checkpoint. Each
request in a batch gets its own row and its own terminal status,
independent of every other request - `CollectionService.run_batch`
iterates requests and never lets one exception cancel the rest.

## Raw observation lifecycle

`RawObservation` (`app/models/raw_observation.py`) stores a
**structured, already-parsed** representation of what a source
returned (`raw_payload`, JSONB), not raw HTML. Full page HTML would
bloat the database with no auditing benefit once a `payload_hash`
(sha256 of the canonicalized payload) exists for integrity/duplicate
detection, and it risks accidentally retaining session artifacts.
Adapters are responsible for handing back a JSON-serializable dict; no
secrets (cookies, auth tokens, session headers) may ever be written
into this column. Its `status` moves `COLLECTED` -> `NORMALIZED` (a
`FlightQuote` was derived from it) or `COLLECTED` -> `PARSE_FAILED`
(normalization raised, recorded as a `PARSER_ERROR`).

## Synthetic data policy

`MockSourceAdapter` (`app/collection/adapters/mock.py`) is the only
adapter with `SourceStatus.IMPLEMENTED`. It never makes a network call
and always returns the same deterministic fare for the same request.
Every observation it produces carries `DataProvenance.SYNTHETIC`
end-to-end - on the `RawObservation` row, and on the `FlightQuote` row
derived from it - so it can never be mistaken for a real collected fare
anywhere downstream (see `app.core.enums` module docstring for why
provenance and quality are kept as separate, orthogonal fields).

## Logging

`app.collection.service` logs structured events (`collection_started`,
`collection_completed`, `collection_failed`, `collection_blocked`) with
`source`, `route`, `lead_days`, `duration_s`, `records_found`,
`records_persisted`, and `error_type`. It never logs passwords, tokens,
cookies, or other session/header detail - there is nothing in the
collection pipeline that ever holds those in the first place.
