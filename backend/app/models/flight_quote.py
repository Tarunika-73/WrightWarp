"""Mongo document shape for the ``flight_quotes`` collection.

This is deliberately *not* a flat row: fare components, availability,
and quality/provenance decisions are natural sub-documents, and nesting
them means a query or a future export can pull `fare` or `quality` as
one unit instead of reconstructing it from a dozen flat columns. The
canonical, strongly-validated flat shape API callers and the collection
pipeline actually work with is ``app.schemas.flight_quote.FlightQuoteCreate``
- ``app.repositories.flight_quote_repository`` is the only place that
maps between the two, in both directions.
"""
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import AvailabilityStatus, CabinClass, DataProvenance, QualityStatus, SourceType


class SourceRef(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    type: SourceType


class RouteRef(BaseModel):
    origin: str
    destination: str


class TravelInfo(BaseModel):
    """``travel_date`` is a midnight-UTC ``datetime`` - BSON has no ``date`` type."""

    travel_date: datetime
    # IST calendar date of observation, stored as midnight-UTC datetime.
    observation_date: datetime | None = None
    departure_datetime: datetime | None = None
    arrival_datetime: datetime | None = None
    lead_days: int


class FlightInfo(BaseModel):
    airline_code: str | None = None
    flight_number: str | None = None
    stops: int | None = None


class FareBreakdown(BaseModel):
    base_fare: float | None = None
    taxes: float | None = None
    airport_charges: float | None = None
    user_development_fee: float | None = None
    convenience_fee: float | None = None
    fuel_surcharge: float | None = None
    baggage_fee: float | None = None
    seat_fee: float | None = None
    meal_fee: float | None = None
    other_fees: float | None = None
    total_fare: float | None = None
    currency: str = "INR"
    components_available: list[str] = Field(default_factory=list)


class FareAttributes(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    cabin_class: CabinClass = CabinClass.ECONOMY
    fare_family: str | None = None
    refundable: bool | None = None
    baggage_included: bool | None = None


class AvailabilityInfo(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    status: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    cancellation_status: str | None = None


class QualityInfo(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    status: QualityStatus = QualityStatus.RAW
    score: float | None = None
    reason: str | None = None
    flags: list[str] = Field(default_factory=list)
    robust_z: float | None = None
    rules_version: str | None = None


class ProvenanceInfo(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    data_type: DataProvenance
    collected_at: datetime
    raw_observation_id: str | None = None
    raw_quote_hash: str | None = None
    normalization_version: str | None = None
    extraction_version: str | None = None


class FlightQuoteDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = Field(default=None, alias="_id")
    search_run_id: str
    source: SourceRef
    route: RouteRef
    travel: TravelInfo
    flight: FlightInfo
    fare: FareBreakdown
    fare_attributes: FareAttributes
    availability: AvailabilityInfo
    quality: QualityInfo
    provenance: ProvenanceInfo
    # sha256 identity used for duplicate detection (app.quality.engine.compute_dedup_key).
    dedup_key: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
