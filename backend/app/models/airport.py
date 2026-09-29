from pydantic import BaseModel, ConfigDict, Field


class AirportDocument(BaseModel):
    """Mongo document shape for the ``airports`` reference collection."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = Field(default=None, alias="_id")
    iata_code: str
    name: str
    city: str
    state: str | None = None
    active: bool = True
