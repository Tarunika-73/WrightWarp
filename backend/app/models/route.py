from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class RouteDocument(BaseModel):
    """Mongo document shape for the ``routes`` collection.

    Denormalized: ``origin``/``destination`` are IATA codes directly
    rather than foreign keys into ``airports`` - a document database has
    no join, and every consumer of a route (collection requests, index
    cells) wants the code, not an internal id. ``weight`` stays ``None``
    until an official DGCA/MoSPI market-share figure is supplied - see
    ``docs/architecture/data_model.md``; nothing in this migration
    invents one.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = Field(default=None, alias="_id")
    route_code: str
    origin: str
    destination: str
    weight: float | None = None
    active: bool = True
    source_reference: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
