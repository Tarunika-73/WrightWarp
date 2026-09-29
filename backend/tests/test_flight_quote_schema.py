from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.core.enums import AvailabilityStatus, DataProvenance, QualityStatus
from app.schemas.flight_quote import FlightQuoteCreate


def _base_quote(**overrides):
    search_dt = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    payload = dict(
        search_run_id="000000000000000000000001",
        source="6E",
        origin="DEL",
        destination="BOM",
        travel_date=date(2026, 1, 8),
        search_datetime=search_dt,
        lead_days=7,
        total_fare=5000.0,
        base_fare=4200.0,
        taxes=800.0,
        currency="INR",
        availability_status=AvailabilityStatus.AVAILABLE,
        provenance=DataProvenance.SYNTHETIC,
        quality_status=QualityStatus.RAW,
    )
    payload.update(overrides)
    return payload


def test_valid_quote_is_accepted():
    quote = FlightQuoteCreate(**_base_quote())
    assert quote.total_fare == 5000.0


def test_lowercase_iata_codes_are_uppercased():
    quote = FlightQuoteCreate(**_base_quote(origin="del", destination="bom"))
    assert quote.origin == "DEL"
    assert quote.destination == "BOM"


def test_origin_equals_destination_rejected():
    with pytest.raises(ValidationError):
        FlightQuoteCreate(**_base_quote(origin="DEL", destination="DEL"))


@pytest.mark.parametrize("lead_days", [0, 2, 3, 14, 60])
def test_unsupported_lead_days_rejected(lead_days):
    with pytest.raises(ValidationError):
        FlightQuoteCreate(**_base_quote(lead_days=lead_days))


def test_negative_base_fare_rejected():
    with pytest.raises(ValidationError):
        FlightQuoteCreate(**_base_quote(base_fare=-100.0))


def test_negative_total_fare_rejected():
    with pytest.raises(ValidationError):
        FlightQuoteCreate(**_base_quote(total_fare=-1.0))


def test_travel_date_before_search_date_rejected():
    with pytest.raises(ValidationError):
        FlightQuoteCreate(
            **_base_quote(
                search_datetime=datetime(2026, 1, 10, tzinfo=timezone.utc),
                travel_date=date(2026, 1, 5),
            )
        )


def test_available_quote_without_total_fare_rejected():
    with pytest.raises(ValidationError):
        FlightQuoteCreate(
            **_base_quote(availability_status=AvailabilityStatus.AVAILABLE, total_fare=None)
        )


def test_sold_out_quote_without_fare_is_allowed():
    quote = FlightQuoteCreate(
        **_base_quote(
            availability_status=AvailabilityStatus.SOLD_OUT,
            total_fare=None,
            base_fare=None,
            taxes=None,
        )
    )
    assert quote.total_fare is None


def test_invalid_quote_requires_reason():
    with pytest.raises(ValidationError):
        FlightQuoteCreate(
            **_base_quote(
                availability_status=AvailabilityStatus.INVALID_QUOTE,
                total_fare=None,
                quality_reason=None,
            )
        )


def test_invalid_quote_with_reason_is_allowed():
    quote = FlightQuoteCreate(
        **_base_quote(
            availability_status=AvailabilityStatus.INVALID_QUOTE,
            total_fare=None,
            quality_reason="Fare unbundling failed: no base_fare component found",
        )
    )
    assert quote.quality_reason is not None


def test_missing_currency_rejected():
    with pytest.raises(ValidationError):
        FlightQuoteCreate(**_base_quote(currency=""))


def test_synthetic_provenance_is_preserved():
    quote = FlightQuoteCreate(**_base_quote(provenance=DataProvenance.SYNTHETIC))
    assert quote.provenance == DataProvenance.SYNTHETIC.value
