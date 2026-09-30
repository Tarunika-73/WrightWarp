"""Response schemas for the statistical API (index, backtest, fares)."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class IndexPoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    period: str = Field(description="Period key: YYYY-MM-DD (daily), YYYY-Www (ISO week), YYYY-MM (monthly)")
    start: date
    value: float = Field(description="Index value, base year = 100")
    n_obs: int | None = None
    n_items: int | None = None
    n_routes: int | None = None
    price: float | None = Field(default=None, description="Implied geometric-mean fare level, INR (route series)")


class IndexSeriesOut(BaseModel):
    series_id: str
    run_id: str
    methodology: str
    frequency: str
    scope: str
    scope_key: str
    base_year: int
    base_value: float
    data_label: str = Field(description="DEMO (simulated inputs) or REAL")
    weighting_version: str
    weighting_label: str = Field(description="DEMO or OFFICIAL")
    calculation_version: str
    calculated_at: datetime
    points: list[IndexPoint]


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class BookingWindowFare(BaseModel):
    lead_days: int
    window: str
    observation_date: date
    observations: int
    valid_observations: int
    min_fare: float | None
    median_fare: float | None
    geometric_mean_fare: float | None
    max_fare: float | None
    currency: str = "INR"
    by_airline: list[dict]
