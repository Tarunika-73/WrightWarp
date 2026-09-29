from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import CollectionErrorType


class CollectionErrorDocument(BaseModel):
    """Mongo document shape for the ``collection_errors`` collection.

    ``CollectionResult.errors`` (app.schemas.collection) is what a caller
    of ``CollectionService`` sees immediately; this collection is the
    durable, queryable record of the same errors, kept even after the
    in-memory ``CollectionResult`` is gone - e.g. "how many RATE_LIMITED
    errors did source X produce this week". Never carries a traceback,
    headers, cookies, or other session detail - the same rule as
    ``CollectionError`` itself.
    """

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    id: str | None = Field(default=None, alias="_id")
    search_run_id: str
    source: str
    error_type: CollectionErrorType
    message: str
    detail: str | None = None
    retryable: bool = False
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
