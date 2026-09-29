from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import SearchRunStatus


class SearchRunDocument(BaseModel):
    """Mongo document shape for the ``search_runs`` collection.

    This is the audit anchor and Phase 2 checkpoint unit, unchanged in
    spirit from Phase 1/2: one document per collection attempt, holding
    what was searched, when, and how it ended - independent of whether
    any ``flight_quotes`` documents were produced.

    ``travel_date`` is stored as a midnight-UTC ``datetime`` - BSON has no
    ``date`` type. ``app.db.bson_utils`` is the one place that converts to
    and from ``datetime.date`` at the API/schema boundary.
    """

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    id: str | None = Field(default=None, alias="_id")
    source: str
    origin: str | None = None
    destination: str | None = None
    route: str | None = None
    travel_date: datetime | None = None
    lead_days: int | None = None
    status: SearchRunStatus = SearchRunStatus.PENDING
    started_at: datetime
    completed_at: datetime | None = None
    records_found: int = 0
    records_valid: int = 0
    error_message: str | None = None
    request_hash: str | None = None
