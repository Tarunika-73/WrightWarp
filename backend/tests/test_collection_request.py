from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.collection import CollectionRequest


def _future_travel_date(days: int = 30) -> date:
    return date.today() + timedelta(days=days)


def _request(**overrides):
    payload = dict(
        source_id="MOCK",
        origin="DEL",
        destination="BOM",
        travel_date=_future_travel_date(),
        lead_days=15,
        passenger_count=1,
    )
    payload.update(overrides)
    return payload


def test_valid_request_is_accepted():
    request = CollectionRequest(**_request())
    assert request.origin == "DEL"
    assert request.destination == "BOM"


def test_lowercase_iata_codes_are_uppercased():
    request = CollectionRequest(**_request(origin="del", destination="bom"))
    assert request.origin == "DEL"
    assert request.destination == "BOM"


def test_same_origin_and_destination_rejected():
    with pytest.raises(ValidationError):
        CollectionRequest(**_request(origin="DEL", destination="DEL"))


@pytest.mark.parametrize("lead_days", [0, 2, 3, 14, 60, -1])
def test_unsupported_lead_days_rejected(lead_days):
    with pytest.raises(ValidationError):
        CollectionRequest(**_request(lead_days=lead_days))


@pytest.mark.parametrize("lead_days", [1, 7, 15, 30, 45])
def test_supported_lead_days_accepted(lead_days):
    request = CollectionRequest(**_request(lead_days=lead_days))
    assert request.lead_days == lead_days


@pytest.mark.parametrize("passenger_count", [0, -1])
def test_invalid_passenger_count_rejected(passenger_count):
    with pytest.raises(ValidationError):
        CollectionRequest(**_request(passenger_count=passenger_count))


def test_travel_date_in_the_past_rejected():
    with pytest.raises(ValidationError):
        CollectionRequest(**_request(travel_date=date.today() - timedelta(days=1)))


def test_non_alphabetic_airport_code_rejected():
    with pytest.raises(ValidationError):
        CollectionRequest(**_request(origin="D3L"))


def test_default_cabin_class_is_economy():
    request = CollectionRequest(**_request())
    assert request.cabin_class == "ECONOMY"
