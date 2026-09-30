"""raw payload -> normalized fare -> quality decision -> canonical FlightQuoteCreate.

The one function (``process_observation``) that both the live
``CollectionService`` and the historical demo backfill run every raw
observation through, so a quote's quality/normalization never depends on
which path produced it.
"""
from dataclasses import dataclass
from datetime import date, datetime

from pydantic import ValidationError

from app.core.enums import AvailabilityStatus, CabinClass, DataProvenance, QualityStatus
from app.normalization.fares import NORMALIZATION_VERSION, NormalizedFare, normalize_fare, observation_date, to_utc
from app.quality.engine import FareObservation, QualityAssessment, QualityContext, assess
from app.schemas.flight_quote import FlightQuoteCreate


@dataclass(frozen=True)
class ObservationContext:
    """What the collector knew when it captured a payload (the request side)."""

    search_run_id: str
    source: str
    origin: str
    destination: str
    travel_date: date
    lead_days: int
    search_datetime: datetime
    provenance: DataProvenance
    cabin_class: str = CabinClass.ECONOMY.value
    raw_observation_id: str | None = None
    raw_payload_hash: str | None = None
    extraction_version: str | None = None


@dataclass
class ProcessedObservation:
    fare: NormalizedFare
    observation: FareObservation
    assessment: QualityAssessment
    quote: FlightQuoteCreate | None
    # Set when the observation could not be expressed as a canonical quote
    # at all (e.g. unsupported booking window). The raw observation keeps
    # the quality decision so nothing is lost.
    quote_error: str | None = None


def _upper_or_none(value: object) -> str | None:
    return value.strip().upper() if isinstance(value, str) and value.strip() else None


def _availability(raw: dict) -> str:
    value = raw.get("availability_status")
    if isinstance(value, AvailabilityStatus):
        return value.value
    if isinstance(value, str) and value.upper() in AvailabilityStatus.__members__:
        return value.upper()
    return AvailabilityStatus.UNKNOWN.value


def to_fare_observation(raw: dict, ctx: ObservationContext) -> tuple[FareObservation, NormalizedFare]:
    fare = normalize_fare(raw)
    search_utc, _assumed_ist = to_utc(ctx.search_datetime)
    cabin = raw.get("cabin_class", ctx.cabin_class)
    cabin_value = cabin.value if isinstance(cabin, CabinClass) else cabin
    obs = FareObservation(
        source=ctx.source,
        origin=_upper_or_none(raw.get("origin")) or ctx.origin,
        destination=_upper_or_none(raw.get("destination")) or ctx.destination,
        travel_date=ctx.travel_date,
        search_datetime=search_utc,
        observation_date=observation_date(search_utc),
        lead_days=ctx.lead_days,
        airline_code=_upper_or_none(raw.get("airline_code")),
        flight_number=_upper_or_none(raw.get("flight_number")),
        cabin_class=cabin_value,
        availability_status=_availability(raw),
        fare=fare,
    )
    return obs, fare


def build_quote(raw: dict, ctx: ObservationContext, obs: FareObservation, fare: NormalizedFare, assessment: QualityAssessment) -> FlightQuoteCreate:
    """Raises ``pydantic.ValidationError`` if the observation cannot be a canonical quote."""
    c = fare.components
    return FlightQuoteCreate(
        search_run_id=ctx.search_run_id,
        source=ctx.source,
        airline_code=obs.airline_code,
        flight_number=obs.flight_number,
        origin=obs.origin,
        destination=obs.destination,
        travel_date=obs.travel_date,
        search_datetime=obs.search_datetime,
        observation_date=obs.observation_date,
        lead_days=obs.lead_days,
        cabin_class=obs.cabin_class or CabinClass.ECONOMY.value,
        fare_family=raw.get("fare_family"),
        stops=raw.get("stops"),
        base_fare=c["base_fare"],
        taxes=c["taxes"],
        airport_charges=c["airport_charges"],
        user_development_fee=c["user_development_fee"],
        convenience_fee=c["convenience_fee"],
        fuel_surcharge=c["fuel_surcharge"],
        baggage_fee=c["baggage_fee"],
        seat_fee=c["seat_fee"],
        meal_fee=c["meal_fee"],
        other_fees=c["other_fees"],
        total_fare=fare.total_fare,
        # Unknown currency is recorded as the 3-letter placeholder "XXX"
        # (ISO 4217 "no currency"), never silently assumed to be INR.
        currency=fare.currency or "XXX",
        components_available=fare.components_available,
        availability_status=obs.availability_status,
        refundable=raw.get("refundable"),
        baggage_included=raw.get("baggage_included"),
        raw_quote_hash=ctx.raw_payload_hash,
        raw_observation_id=ctx.raw_observation_id,
        provenance=ctx.provenance,
        quality_status=assessment.status,
        quality_score=assessment.score,
        quality_reason=assessment.reason,
        quality_flags=assessment.flags,
        quality_robust_z=assessment.robust_z,
        quality_rules_version=assessment.rules_version,
        dedup_key=assessment.dedup_key,
        normalization_version=NORMALIZATION_VERSION,
        extraction_version=ctx.extraction_version,
    )


def process_observation(
    raw: dict,
    ctx: ObservationContext,
    quality_context: QualityContext | None = None,
    *,
    now: datetime | None = None,
) -> ProcessedObservation:
    obs, fare = to_fare_observation(raw, ctx)
    assessment = assess(obs, quality_context, now=now)
    try:
        quote = build_quote(raw, ctx, obs, fare, assessment)
        return ProcessedObservation(fare=fare, observation=obs, assessment=assessment, quote=quote)
    except ValidationError as exc:
        if assessment.status not in (QualityStatus.REJECTED, QualityStatus.MISSING):
            # The rules passed it but the canonical schema did not: surface
            # that as a rejection rather than losing the reason.
            assessment.status = QualityStatus.REJECTED
            assessment.score = 0.0
            assessment.reasons.append("schema_validation_failed")
        messages = "; ".join(err.get("msg", "") for err in exc.errors())
        return ProcessedObservation(fare=fare, observation=obs, assessment=assessment, quote=None, quote_error=messages)
