from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import DataProvenance, SourceStatus, SourceType


class SourceDocument(BaseModel):
    """Mongo document shape for the ``sources`` collection.

    This collection is a *read mirror* of ``app.core.sources.ALL_SOURCES``
    (kept in sync by ``SourceRepository.sync_registry`` at startup), not
    an independent source of truth: compliance status is a reviewed,
    code-level decision (see ``docs/architecture/source-adapters.md``),
    and must not be flippable by writing to the database. It exists so
    ``GET /api/v1/sources`` and any future query ("list every enabled
    OTA") can go through the same repository pattern as every other
    collection, and so the required ``sources`` collection is real and
    queryable rather than only ever living in a Python module.
    ``CollectionService`` still checks compliance against the static
    registry directly, never against this collection.
    """

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    id: str | None = Field(default=None, alias="_id")
    source_id: str
    display_name: str
    source_type: SourceType
    enabled: bool
    status: SourceStatus
    robots_url: str | None
    terms_url: str | None
    rate_limit_per_minute: float
    requires_browser: bool
    requires_terms_review: bool
    requires_robots_review: bool
    notes: str
    data_provenance: DataProvenance = DataProvenance.REAL
