"""Turns one raw, source-specific payload into a canonical ``FlightQuoteCreate``.

This is the only place that knows how to read an adapter's raw payload
shape. Every adapter, regardless of source, converges here before
anything is persisted as a ``FlightQuote`` - which is what lets the
Index Engine (Phase 3+) consume one uniform schema no matter which
airline or OTA an observation came from.

A pure function - no database access. Since the canonical schema now
carries IATA codes directly (see ``app.schemas.flight_quote``) rather
than internal airport-id foreign keys, there is no lookup to perform.
"""
from datetime import datetime

from app.core.enums import AvailabilityStatus, DataProvenance, QualityStatus
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
    try:
        return FlightQuoteCreate(
            search_run_id=search_run_id,
            source=source,
            airline_code=raw_payload.get("airline_code"),
            flight_number=raw_payload.get("flight_number"),
            origin=raw_payload.get("origin", request.origin),
            destination=raw_payload.get("destination", request.destination),
            travel_date=request.travel_date,
            search_datetime=search_datetime,
            lead_days=request.lead_days,
            cabin_class=raw_payload.get("cabin_class", request.cabin_class),
            stops=raw_payload.get("stops"),
            base_fare=raw_payload.get("base_fare"),
            taxes=raw_payload.get("taxes"),
            total_fare=raw_payload.get("total_fare"),
            currency=raw_payload.get("currency", "INR"),
            availability_status=raw_payload.get("availability_status", AvailabilityStatus.UNKNOWN.value),
            raw_observation_id=raw_observation_id,
            provenance=provenance,
            quality_status=QualityStatus.RAW,
        )
    except Exception as exc:  # noqa: BLE001 - reclassified into NormalizationError for the caller
        raise NormalizationError(str(exc)) from exc
