from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import DataProvenance, RawObservationStatus


class RawObservationDocument(BaseModel):
    """Mongo document shape for the ``raw_observations`` collection.

    ``raw_payload`` stores a structured (already-parsed) representation
    of the source response, not raw HTML - full page HTML would bloat
    the database for no auditing benefit once ``payload_hash`` exists
    for integrity/duplicate detection, and risks retaining session
    artifacts. If a future source's raw payload were ever too large to
    embed reasonably in a document (MongoDB's hard document limit is
    16MB), the payload would go to GridFS or an object store with only a
    reference (bucket key + hash) kept here - no source has needed that
    yet, so it is not implemented speculatively. No secrets (cookies,
    auth tokens, session headers) may ever be written into this
    collection.
    """

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    id: str | None = Field(default=None, alias="_id")
    search_run_id: str
    source: str
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_parameters: dict[str, Any]
    raw_payload: dict[str, Any]
    payload_hash: str
    status: RawObservationStatus = RawObservationStatus.COLLECTED
    provenance: DataProvenance = DataProvenance.REAL
    # Quality decision recorded on the raw observation too, so an
    # observation that could not become a FlightQuote (e.g. REJECTED for
    # an unsupported booking window) still carries *why*.
    quality_status: str | None = None
    quality_reason: str | None = None
    extraction_version: str | None = None
