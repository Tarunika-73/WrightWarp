"""Turns one raw, source-specific payload into a canonical ``FlightQuoteCreate``.

Kept as the Phase 2 entry point for callers that hold a
``CollectionRequest``; the actual work - fare-component normalization
and the data-quality decision - lives in ``app.normalization.pipeline``,
which ``CollectionService`` and the demo backfill call directly. Every
adapter, regardless of source, converges there before anything is
persisted as a ``FlightQuote``.
"""
from datetime import datetime

from app.core.enums import DataProvenance
from app.normalization.pipeline import ObservationContext, process_observation
from app.schemas.collection import CollectionRequest
from app.schemas.flight_quote import FlightQuoteCreate


class NormalizationError(Exception):
    """Raised when a raw payload cannot be converted into a valid FlightQuote."""


def normalize(
    *,
    search_run_id: str,
    source: str,
    request: CollectionRequest,
    raw_payload: dict,
    provenance: DataProvenance,
    search_datetime: datetime,
    raw_observation_id: str | None = None,
) -> FlightQuoteCreate:
    ctx = ObservationContext(
        search_run_id=search_run_id,
        source=source,
        origin=request.origin,
        destination=request.destination,
        travel_date=request.travel_date,
        lead_days=request.lead_days,
        cabin_class=request.cabin_class,
        search_datetime=search_datetime,
        provenance=provenance,
        raw_observation_id=raw_observation_id,
    )
    processed = process_observation(raw_payload, ctx)
    if processed.quote is None:
        raise NormalizationError(processed.quote_error or processed.assessment.reason or "normalization failed")
    return processed.quote
