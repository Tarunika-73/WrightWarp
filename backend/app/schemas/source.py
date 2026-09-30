from pydantic import BaseModel, ConfigDict

from app.core.enums import DataProvenance, SourceStatus, SourceType


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

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
