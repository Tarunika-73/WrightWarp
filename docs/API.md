# API Reference

Interactive documentation is served by the application at `/docs` (Swagger UI), `/redoc`, and
`/openapi.json`. All data endpoints live under `/api/v1`.

## Conventions

- **Labels.** Index, backtest, and overview responses carry `data_label` (`DEMO` or `REAL`) and
  `weighting_label` (`DEMO` or `OFFICIAL`).
- **Pagination.** `page` (1-based) and `page_size` (max 500). Responses have the shape
  `{"items": [...], "page": {"page", "page_size", "total", "pages"}}`.
- **Dates.** ISO 8601. `observation_date`, `date_from`, and `date_to` are IST calendar days.
  Timestamps are UTC with an offset.
- **Errors.** Every error has the same shape:

```json
{"detail": "Route 'GOI-IXZ' is not a monitored route",
 "error": {"code": "NOT_FOUND", "message": "…", "request_id": "…", "details": null}}
```

| HTTP | code | When |
|---|---|---|
| 400 | `BAD_REQUEST` | unknown methodology, unsupported booking window, range too long |
| 401 | `UNAUTHORIZED` | missing or wrong bearer token on a protected endpoint |
| 404 | `NOT_FOUND` | unknown route, quote, collection, or path |
| 422 | `VALIDATION_ERROR` | request schema violation (`details` lists fields) |
| 503 | `INDEX_NOT_COMPUTED` | no index run exists yet |
| 503 | `DATABASE_ERROR` | MongoDB unavailable |
| 503 | `NOT_CONFIGURED` | `CRON_SECRET` not set |
| 500 | `INTERNAL_ERROR` | unexpected error (no details are exposed) |

## Endpoints

### Health and metadata
| Method | Path | Description |
|---|---|---|
| GET | `/health` | liveness (no DB dependency) |
| GET | `/health/db` | MongoDB ping |
| GET | `/api/v1/meta` | demo mode, data notice, base year, windows, routes, methodologies, weighting |
| GET | `/api/v1/stats/overview` | dashboard headline: current index, changes, trends, movers, windows, quality, sources, last collection |

### Sources, routes, collections
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/sources` | registry with compliance status and provenance |
| GET | `/api/v1/routes` | monitored routes, airports, weight shares, observation coverage |
| GET | `/api/v1/routes/{route_code}` | one route |
| GET | `/api/v1/collections?source&status&route&page&page_size` | collection runs (checkpoints), newest first |
| POST | `/api/v1/collections` | run one collection: `{"source_id","origin","destination","travel_date","lead_days"}`. Uncleared sources return `outcome: BLOCKED`. |
| GET | `/api/v1/collections/{id}` | one run |

### Fares
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/fares` (alias `/api/v1/quotes`) | normalized quotes; filters `route, travel_date, lead_days, date_from, date_to, source, quality_status, airline` |
| GET | `/api/v1/quotes/{id}` | one quote |
| GET | `/api/v1/quotes/{id}/provenance` | quote, raw observation (with payload hash), and collection run |
| GET | `/api/v1/fares/booking-window?route&travel_date` | for each window T+X: fares for that travel date observed X days earlier (min/median/geometric mean/max, per carrier) |
| GET | `/api/v1/fares/booking-window/compare?route&date_from&date_to` | average fare and premium vs the longest window |
| GET | `/api/v1/fares/daily?route&date_from&date_to` | daily geometric-mean fare per window |

Example: *What does DEL-BOM cost when bought 15 days before travel on 2026-10-20?*
`GET /api/v1/fares/booking-window?route=DEL-BOM&travel_date=2026-10-20` returns the `T+15` row.

### Index
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/index?methodology&frequency&start&end&limit` | overall series (default LASPEYRES, monthly) |
| GET | `/api/v1/index/daily`, `/weekly`, `/monthly` | frequency shortcuts (`methodology`, `start`, `end`, `limit`) |
| GET | `/api/v1/index/route/{route}?frequency&lead_days` | route (or route × window) elementary index; points include `price` (INR) |
| GET | `/api/v1/index/booking-window?lead_days&methodology&frequency` | one window across routes |
| GET | `/api/v1/index/methodologies?frequency` | all four formulas side by side |
| GET | `/api/v1/index/series` | catalogue of series in the current run |
| GET | `/api/v1/index/runs/current` | reproducibility record |
| GET | `/api/v1/index/trace?route&observation_date&lead_days` | index point, cells, and observations with quality and inclusion |

Methodologies: `LASPEYRES` (headline), `PAASCHE`, `FISHER`, `JEVONS`. Frequencies: `daily`,
`weekly`, `monthly`.

### Quality and backtest
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/quality/summary?days` | counts by status and source, top rules, daily timeline |
| GET | `/api/v1/quality/rules` | rules, thresholds, severity order |
| GET | `/api/v1/backtest` | latest backtest report |
| POST | `/api/v1/backtest/run` | recompute series + backtest from existing cells (protected) |

### Scheduled / admin (require `Authorization: Bearer $CRON_SECRET`)
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/cron/daily` | collection pass over all cleared sources + index recomputation (Vercel Cron) |
| POST | `/api/v1/admin/recompute-index` | rebuild all cells and recompute everything |
