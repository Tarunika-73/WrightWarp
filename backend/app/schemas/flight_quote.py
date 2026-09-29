"""Pydantic schemas for FlightQuote: the canonical, strongly-validated shape
every source adapter's output converges to, independent of MongoDB.

Kept flat and IATA-code-based (not nested, not airport-id-based) because
this is the schema the collection pipeline and any API caller actually
work with; ``app.repositories.flight_quote_repository`` is the only place
that maps it to/from the nested ``FlightQuoteDocument`` Mongo shape.
"""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import AvailabilityStatus, CabinClass, DataProvenance, QualityStatus
from app.core.lead_time import is_supported_lead_day
from app.core.validators import validate_iata_code


class FlightQuoteBase(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    search_run_id: str
    source: str

    airline_code: str | None = None
    flight_number: str | None = None
    origin: str = Field(min_length=3, max_length=3)
    destination: str = Field(min_length=3, max_length=3)

    departure_datetime: datetime | None = None
    arrival_datetime: datetime | None = None
    travel_date: date
    search_datetime: datetime
    lead_days: int

    cabin_class: CabinClass = CabinClass.ECONOMY
    fare_family: str | None = None
    stops: int | None = Field(default=None, ge=0)

    base_fare: float | None = Field(default=None, ge=0)
    taxes: float | None = Field(default=None, ge=0)
    user_development_fee: float | None = Field(default=None, ge=0)
    convenience_fee: float | None = Field(default=None, ge=0)
    fuel_surcharge: float | None = Field(default=None, ge=0)
    baggage_fee: float | None = Field(default=None, ge=0)
    seat_fee: float | None = Field(default=None, ge=0)
    meal_fee: float | None = Field(default=None, ge=0)
    other_fees: float | None = Field(default=None, ge=0)
    total_fare: float | None = Field(default=None, ge=0)
    currency: str = Field(min_length=3, max_length=3)

    availability_status: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    cancellation_status: str | None = None
    refundable: bool | None = None
    baggage_included: bool | None = None

    raw_quote_hash: str | None = None
    raw_observation_id: str | None = None
    provenance: DataProvenance
    quality_status: QualityStatus = QualityStatus.RAW
    quality_score: float | None = Field(default=None, ge=0, le=1)
    quality_reason: str | None = None

    @field_validator("origin", "destination")
    @classmethod
    def uppercase_iata(cls, v: str) -> str:
        return validate_iata_code(v)

    @model_validator(mode="after")
    def check_origin_destination(self) -> "FlightQuoteBase":
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")
        return self

    @model_validator(mode="after")
    def check_lead_days_supported(self) -> "FlightQuoteBase":
        if not is_supported_lead_day(self.lead_days):
            raise ValueError(f"lead_days={self.lead_days} is not a supported lead-time window")
        return self

    @model_validator(mode="after")
    def check_travel_date_not_before_search(self) -> "FlightQuoteBase":
        if self.travel_date < self.search_datetime.date():
            raise ValueError("travel_date must not precede search_datetime")
        return self

    @model_validator(mode="after")
    def check_available_quotes_have_fare(self) -> "FlightQuoteBase":
        status = self.availability_status
        status_value = status.value if isinstance(status, AvailabilityStatus) else status
        if status_value == AvailabilityStatus.AVAILABLE.value and self.total_fare is None:
            raise ValueError("AVAILABLE quotes must carry a total_fare")
        return self

    @model_validator(mode="after")
    def check_rejected_quotes_have_reason(self) -> "FlightQuoteBase":
        status = self.availability_status
        status_value = status.value if isinstance(status, AvailabilityStatus) else status
        quality = self.quality_status
        quality_value = quality.value if isinstance(quality, QualityStatus) else quality
        needs_reason = status_value == AvailabilityStatus.INVALID_QUOTE.value or (
            quality_value == QualityStatus.REJECTED.value
        )
        if needs_reason and not self.quality_reason:
            raise ValueError("REJECTED / INVALID_QUOTE observations must retain a quality_reason")
        return self


class FlightQuoteCreate(FlightQuoteBase):
    pass


class FlightQuoteRead(FlightQuoteBase):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: str
    created_at: datetime
