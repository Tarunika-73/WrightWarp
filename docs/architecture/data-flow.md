# WrightWarp Phase 2 — Data Flow

## One collection request, end to end

```
                      POST /api/v1/collections
                      { source_id, origin, destination,
                        travel_date, lead_days, ... }
                                |
                                v
                      CollectionRequest (validated)
                                |
                                v
                 +---  CollectionService.run()  ---+
                 |                                  |
                 |  1. create SearchRun (RUNNING)   |
                 |  2. look up source_id in the     |
                 |     registry (app.core.sources)  |
                 |  3. compliance check:            |
                 |     IMPLEMENTED + enabled?  ---- NO --> SearchRun=BLOCKED
                 |     |                            |      CollectionResult(outcome=BLOCKED)
                 |    YES                           |
                 |  4. RateLimiter.acquire(source)  |
                 |  5. AdapterRegistry.get(source)  |
                 |  6. adapter.search(request)      |
                 |     (retried on NETWORK_ERROR /  |
                 |      TIMEOUT / SOURCE_UNAVAILABLE|
                 |      / RATE_LIMITED only)   ----- exhausted --> SearchRun=FAILED
                 |     |                            |
                 |    outcome                       |
                 |  7. no observations? ------------ YES --> SearchRun=NO_RESULTS
                 |     |                            |      CollectionResult(outcome=NO_RESULTS, success=True)
                 |    NO
                 |  8. for each raw observation:
                 |       - persist RawObservation (JSONB payload, hash, provenance)
                 |       - normalize() -> FlightQuoteCreate
                 |       - persist FlightQuote
                 |       - on normalization failure: mark RawObservation
                 |         PARSE_FAILED, record a PARSER_ERROR, keep going
                 |  9. SearchRun = SUCCESS (all normalized) or
                 |     PARTIAL (some failed) - commit
                 +-----------------------------------+
                                |
                                v
                      CollectionResult (returned to caller)
```

## Where each table fits

```
        source registry              (app/core/sources.py - static config,
        (compliance metadata)          not a table)
              |
              | source_id (string, not an FK)
              v
        search_runs   <---------------  one row per CollectionRequest attempt
              |  ^                      (the checkpoint + audit anchor)
   FK search_run_id   FK search_run_id
              |  |
              v  |
   raw_observations  flight_quotes    <-- both FK back to the same search_run,
   (JSONB payload,       (canonical,       so any quote is traceable to the
    payload_hash,         normalized        exact raw payload and request
    provenance,           schema, shared    that produced it
    COLLECTED/            with Phase 1)
    NORMALIZED/
    PARSE_FAILED)
```

## Compliance short-circuit

A request for a `PENDING_REVIEW` or disabled source never reaches an
adapter at all - step 3 above stops it, and the `SearchRun` still records
the attempt (as `BLOCKED`) for audit purposes. This is what makes it safe
to register every source from the SIH26056 problem statement up front
(`docs/architecture/source-adapters.md`) without any of them being able
to actually run.

## Batch collection (multiple lead-time windows / routes)

```
[DEL-BOM T+1, DEL-BOM T+7, DEL-BOM T+15, DEL-BOM T+30, DEL-BOM T+45]
        |
        v
CollectionService.run_batch(requests)
        |
        +--> run(T+1)  -> SearchRun #1 (e.g. SUCCESS)
        +--> run(T+7)  -> SearchRun #2 (e.g. FAILED - caught, does not stop the batch)
        +--> run(T+15) -> SearchRun #3 (SUCCESS)
        +--> run(T+30) -> SearchRun #4 (SUCCESS)
        +--> run(T+45) -> SearchRun #5 (SUCCESS)
```

Each request is independent: one failing leaves the others' already-
recorded status untouched, because each is its own `SearchRun` row and
`run_batch` catches any unexpected exception per-item rather than letting
it propagate.
