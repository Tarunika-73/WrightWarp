import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.validators import validate_iata_code

ROUTE_CODE_PATTERN = re.compile(r"^[A-Z]{3}-[A-Z]{3}$")


class RouteBase(BaseModel):
    origin: str = Field(min_length=3, max_length=3)
    destination: str = Field(min_length=3, max_length=3)
    route_code: str
    weight: float | None = None
    active: bool = True
    source_reference: str | None = None

    @field_validator("origin", "destination")
    @classmethod
    def uppercase_iata(cls, v: str) -> str:
        return validate_iata_code(v)

    @field_validator("route_code")
    @classmethod
    def validate_route_code_shape(cls, v: str) -> str:
        if not ROUTE_CODE_PATTERN.match(v):
            raise ValueError("route_code must match the pattern XXX-XXX (e.g. DEL-BOM)")
        return v

    @model_validator(mode="after")
    def check_route_code_matches_origin_destination(self) -> "RouteBase":
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")
        expected = f"{self.origin}-{self.destination}"
        if self.route_code != expected:
            raise ValueError(f"route_code {self.route_code!r} does not match origin/destination ({expected!r})")
        return self


class RouteCreate(RouteBase):
    pass


class RouteRead(RouteBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
