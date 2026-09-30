from datetime import datetime, timedelta, timezone

import pytest

from app.normalization.fares import (
    IST,
    FareParseError,
    normalize_currency,
    normalize_fare,
    observation_date,
    parse_amount,
    to_utc,
)


@pytest.mark.parametrize(
    "value, expected",
    [(5234, 5234.0), (5234.567, 5234.57), ("5,234.50", 5234.5), ("₹5,234", 5234.0), ("Rs. 4,999", 4999.0), ("INR 3100", 3100.0), (None, None), ("", None), ("   ", None)],
)
def test_parse_amount_reads_numbers_and_display_strings(value, expected):
    assert parse_amount(value) == expected


@pytest.mark.parametrize("value", ["abc", "12-34", True, [1]])
def test_parse_amount_rejects_garbage(value):
    with pytest.raises(FareParseError):
        parse_amount(value)


def test_currency_normalization():
    assert normalize_currency("inr") == "INR"
    assert normalize_currency("₹") == "INR"
    assert normalize_currency(None, amount_hint="₹4,500") == "INR"
    assert normalize_currency(None, amount_hint=4500) is None
    assert normalize_currency("usd") == "USD"


def test_total_only_source_keeps_total_and_marks_components_unavailable():
    fare = normalize_fare({"total_fare": "₹6,120", "currency": "INR"})
    assert fare.total_fare == 6120.0
    assert fare.components_available == []
    assert all(v is None for v in fare.components.values())
    assert fare.components_complete is False
    assert fare.mandatory_component_sum is None


def test_components_without_total_never_derive_a_total():
    fare = normalize_fare({"base_fare": 4000, "taxes": 200, "airport_charges": 600, "currency": "INR"})
    assert fare.total_fare is None  # not fabricated from the components
    assert fare.components_available == ["base_fare", "taxes", "airport_charges"]
    assert fare.mandatory_component_sum == 4800.0


def test_aliases_and_ancillaries_excluded_from_mandatory_sum():
    fare = normalize_fare({"base": 4000, "tax": 200, "udf": 150, "baggage_fee": 900, "price": 4350, "currency": "INR"})
    assert fare.components["base_fare"] == 4000
    assert fare.components["user_development_fee"] == 150
    assert fare.components["baggage_fee"] == 900
    assert fare.mandatory_component_sum == 4350.0
    assert fare.total_fare == 4350.0


def test_unparseable_component_is_reported_not_guessed():
    fare = normalize_fare({"total_fare": "n/a", "currency": "INR"})
    assert fare.total_fare is None
    assert fare.parse_errors and "total_fare" in fare.parse_errors[0]


def test_naive_timestamps_are_assumed_ist_and_converted_to_utc():
    utc, assumed = to_utc(datetime(2026, 1, 1, 6, 0))
    assert assumed is True
    assert utc == datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc)
    aware, assumed = to_utc(datetime(2026, 1, 1, 6, 0, tzinfo=timezone(timedelta(hours=2))))
    assert assumed is False
    assert aware.utcoffset() == timedelta(0)


def test_observation_date_is_the_ist_calendar_day():
    # 20:00 UTC on 1 Jan is 01:30 IST on 2 Jan.
    assert observation_date(datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc)).isoformat() == "2026-01-02"
    assert observation_date(datetime(2026, 1, 1, 6, 0, tzinfo=IST)).isoformat() == "2026-01-01"
