# `scraper/` — reserved

Phase 2's actual collection framework (contracts, `SourceAdapter`
interface, `MockSourceAdapter`, rate limiter, browser abstraction,
orchestrator) lives in `backend/app/collection/` instead of here, so it
can be called in-process by the FastAPI app (`POST /api/v1/collections`)
and share its SQLAlchemy session, models, and Pydantic schemas directly
with the rest of the backend.

These directories (`adapters/`, `browser/`, `parsers/`, `pipelines/`,
`scheduler/`) are kept as placeholders in case a future phase needs a
standalone scraper/scheduler process decoupled from the API. See
`docs/architecture/data-collection.md` for where each concept actually
lives today.
