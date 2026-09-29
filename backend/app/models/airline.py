from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class AirlineDocument(BaseModel):
    """Mongo document shape for the ``airlines`` reference collection."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = Field(default=None, alias="_id")
    code: str
    name: str
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
