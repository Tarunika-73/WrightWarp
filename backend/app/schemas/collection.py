"""Source-independent collection contracts (Phase 2, Stage A).

These Pydantic models are the vocabulary every source adapter, the
orchestrator, and the API speak: a ``SourceAdapter`` only ever receives a
``CollectionRequest`` and only ever hands back an ``AdapterSearchOutcome``.
Nothing here knows about HTTP, Playwright, or any specific airline/OTA -
that knowledge lives one layer down, in ``app.collection.adapters.*``.
"""
from datetime import date, datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import (
    CabinClass,
    CollectionErrorType,
    CollectionOutcome,
    RawObservationStatus,
    SearchRunStatus,
)
from app.core.lead_time import is_supported_lead_day
from app.core.validators import validate_iata_code

_IATA_PATTERN_LEN = 3


class CollectionRequest(BaseModel):
    """One request to search a single source for a single route/date/lead-time.

    Deliberately expressed in IATA codes rather than internal
    ``airports.id`` primary keys: a collection request is what you would
    hand to a source's search form, and should not need to know about our
    database. ``CollectionRepository`` resolves codes to airport rows only
    at persistence time.
    """

    model_config = ConfigDict(use_enum_values=True)

    source_id: str = Field(min_length=1, max_length=64)
    origin: str = Field(min_length=_IATA_PATTERN_LEN, max_length=_IATA_PATTERN_LEN)
    destination: str = Field(min_length=_IATA_PATTERN_LEN, max_length=_IATA_PATTERN_LEN)
    travel_date: date
    lead_days: int
    passenger_count: int = Field(default=1, ge=1)
    cabin_class: CabinClass = CabinClass.ECONOMY

    @field_validator("origin", "destination")
    @classmethod
    def uppercase_iata(cls, v: str) -> str:
        return validate_iata_code(v)

    @model_validator(mode="after")
    def check_origin_ne_destination(self) -> "CollectionRequest":
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")
        return self

    @model_validator(mode="after")
    def check_lead_days_supported(self) -> "CollectionRequest":
        if not is_supported_lead_day(self.lead_days):
            raise ValueError(f"lead_days={self.lead_days} is not a supported lead-time window")
        return self

    @model_validator(mode="after")
    def check_travel_date_not_in_past(self) -> "CollectionRequest":
        if self.travel_date < datetime.now(timezone.utc).date():
            raise ValueError("travel_date must not be in the past")
        return self


class CollectionError(BaseModel):
    """Structured, loggable description of one thing that went wrong.

    Never carries exception tracebacks, headers, cookies, or other
    session detail - only what's safe to persist and return over the API.
    """

    model_config = ConfigDict(use_enum_values=True)

    error_type: CollectionErrorType
    message: str
    detail: str | None = None
    retryable: bool = False


class AdapterObservation(BaseModel):
    """One raw item an adapter found, before it becomes a persisted ``RawObservation`` row."""

    model_config = ConfigDict(use_enum_values=True)

    raw_payload: dict[str, Any]
    status: RawObservationStatus = RawObservationStatus.COLLECTED


class AdapterSearchOutcome(BaseModel):
    """What ``SourceAdapter.search`` returns: raw findings plus any structured errors.

    ``blocked`` lets an adapter signal, at runtime, that the source itself
    refused the request in a way that indicates a compliance boundary
    (e.g. an HTTP 403 from a robots-disallowed path, or a CAPTCHA wall) -
    this must never be silently retried.
    """

    observations: list[AdapterObservation] = Field(default_factory=list)
    errors: list[CollectionError] = Field(default_factory=list)
    blocked: bool = False


class CollectionResult(BaseModel):
    """Standardized result of one collection attempt (one ``SearchRun``).

    ``success`` is a convenience boolean; ``outcome`` is the field code
    should actually branch on since it distinguishes SUCCESS / PARTIAL /
    FAILED / BLOCKED / NO_RESULTS - a FAILED or BLOCKED attempt is never
    reported as "0 flights found".
    """

    model_config = ConfigDict(use_enum_values=True)

    search_run_id: str | None = None
    success: bool
    outcome: CollectionOutcome
    source: str
    request: CollectionRequest
    started_at: datetime
    completed_at: datetime | None = None
    records_found: int = 0
    raw_observations_persisted: int = 0
    quotes_normalized: int = 0
    errors: list[CollectionError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SearchRunOut(BaseModel):
    """Read-only view of a persisted ``SearchRun`` - what ``GET /collections/{id}`` returns.

    This is the checkpoint record: its ``status`` is exactly what
    ``CollectionService`` left behind, independent of any other request
    in the same batch.
    """

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: str
    source: str
    status: SearchRunStatus
    route: str | None
    travel_date: date | None
    lead_days: int | None
    started_at: datetime
    completed_at: datetime | None
    records_found: int
    records_valid: int
    error_message: str | None
