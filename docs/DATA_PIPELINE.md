# Data Pipeline

```
CollectionRequest ──> compliance gate ──> rate limiter ──> SourceAdapter.search()
                                                                │ raw payloads
                                                                v
                      raw_observations (payload + SHA-256 hash + provenance)   <- stored first, always
                                                                │
                                          fare normalization (app/normalization/fares.py)
                                                                │
                                          quality engine (app/quality/engine.py)
                                                                │
                      flight_quotes (canonical quote + quality decision + provenance links)
                                                                │
                      daily_cells (eligible quotes, geometric mean per day × route × window × carrier)
                                                                │
                      index engine -> index_series / index_runs -> backtest_runs
```

The live `CollectionService` and the historical demo backfill (`app/demo/seed.py`) both call the
same `process_observation()` (`app/normalization/pipeline.py`). A quote's normalization and quality
decision therefore never depend on which path produced it.

## 1. Collection

- `CollectionService` (`app/collection/service.py`) checks the source registry. Only sources that
  are `IMPLEMENTED` **and** enabled are dispatched to. Any other source returns `BLOCKED`.
- A per-source rate limiter enforces minimum spacing between requests. Retries (at most 3, with
  exponential backoff) apply only to transient errors: network, timeout, source unavailable, rate
  limited.
- Each request creates one `search_runs` document, which is the checkpoint: `SUCCESS`, `PARTIAL`,
  `NO_RESULTS`, `FAILED`, or `BLOCKED`.
- Provenance comes from the source's registry entry (`data_provenance`), never from its id:
  `MOCK` gives `SYNTHETIC`, `DEMO_SIM` gives `SIMULATED`, and real sources give `REAL`.

## 2. Fare normalization

`normalize_fare()`:

| Aspect | Rule |
|---|---|
| Components | base fare, taxes, airport charges, UDF, fuel surcharge, convenience fee, other fees (mandatory); baggage, seat, meal (ancillary) |
| Amount parsing | numbers or display strings (`"₹5,234.50"`, `"Rs. 4,999"`). Absent is `None`, never 0. Garbage is a parse error, never a guess. |
| Missing components | stay `None` and are left out of `components_available`. Nothing is estimated. |
| Missing total | never derived from components. The observation becomes `MISSING`. |
| Currency | ISO code, or inferred from a `₹` symbol. Unknown currency is recorded as `XXX`. No FX conversion. |
| Timestamps | converted to UTC. Naive timestamps are taken as IST and the assumption is recorded. |
| Observation date | the IST calendar day of the search, which anchors the index periods |

## 3. Quality engine

Each observation receives exactly **one** status, the most severe one triggered, together with
**every** reason, a score, and flags. Nothing is deleted: the index reads only `VALIDATED` and
`PROVISIONAL`.

Severity: `REJECTED > MISSING > SOLD_OUT > DUPLICATE > REVIEW_REQUIRED > OUTLIER > PROVISIONAL > VALIDATED`

| Rule | Outcome |
|---|---|
| Required fields (source, origin, destination, travel date, search time, lead days) | REJECTED |
| Route: 3-letter uppercase IATA codes, origin ≠ destination | REJECTED |
| Route not in master data | REVIEW_REQUIRED |
| Search timestamp timezone-aware and not in the future | REJECTED |
| Travel date not before observation date, at most 365 days ahead | REJECTED |
| Booking window not configured | REJECTED |
| Declared vs actual lead time differs by more than 1 day | REVIEW_REQUIRED |
| Availability SOLD_OUT / CANCELLED | SOLD_OUT |
| Availability NOT_FOUND / SCRAPE_FAILED | MISSING |
| Available but no total fare | MISSING |
| Fare ≤ 0, outside INR 500–150,000, or unparseable | REJECTED |
| Currency missing | REJECTED |
| Currency not INR | REVIEW_REQUIRED |
| Negative component | REJECTED |
| Mandatory components ≠ total (beyond max(₹1, 1%)) | REVIEW_REQUIRED |
| Duplicate: same source, flight, travel date, cabin, and observation day already seen (SHA-256 `dedup_key`; the fare is deliberately not part of the key) | DUPLICATE |
| Outlier: modified z-score (Iglewicz–Hoaglin) of ln fare vs median/MAD of the route × window's trailing 28 days of cells, \|z\| > 3.5, needs ≥ 10 reference cells | OUTLIER |
| Passed every rule but no reference distribution yet | PROVISIONAL |

The outlier reference excludes the day being judged, so a bad day cannot vouch for itself.

Quality decisions are stored on both the quote (`quality.status/reason/flags/robust_z/rules_version`)
and the raw observation (`quality_status/quality_reason`), so an observation that could not become a
quote still carries its reason.

## 4. Provenance chain

```
index point ──(/index/trace)──> daily cells ──> flight_quotes ──(/quotes/{id}/provenance)──> raw_observations ──> search_runs ──> source registry
```

Every quote stores its `search_run_id`, `raw_observation_id`, `raw_quote_hash` (the SHA-256 of the
raw payload), `normalization_version`, `extraction_version`, `quality.rules_version`, provenance,
and the observation timestamp.

## 5. Scheduled collection

`app/scheduling/daily.py` runs every monitored route × booking window for every cleared source, then
rebuilds the last 3 days of cells and recomputes all index series. It is triggered by Vercel Cron
(`GET /api/v1/cron/daily`, daily at 00:30 UTC / 06:00 IST, `Authorization: Bearer $CRON_SECRET`) or
by `python -m app.cli collect-today`. Re-running a day is safe: repeats are flagged `DUPLICATE`, so
no observation is counted twice.

## 6. Demo backfill

`python -m app.cli seed-demo` regenerates the simulated market's history from 2024-01-01 to
yesterday: daily for the last 120 days and every second day before that. It pushes the history
through the pipeline above and then computes the index and the backtest. Only `DEMO_SIM` documents
are replaced; data from other sources is never touched.
