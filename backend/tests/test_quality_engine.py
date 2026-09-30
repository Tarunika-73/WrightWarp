"""One test (at least) per data-quality rule, plus the combinator."""
import math
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.enums import QualityStatus
from app.normalization.fares import normalize_fare
from app.quality.context import DedupTracker
from app.quality.engine import (
    FareObservation,
    QualityContext,
    ReferenceStats,
    assess,
    check_availability,
    check_currency,
    check_fare_components,
    check_fare_value,
    check_lead_time,
    check_required_fields,
    check_route,
    check_search_timestamp,
    check_travel_date,
    compute_dedup_key,
    reference_from_log_fares,
    robust_z_score,
)

SEARCH = datetime(2026, 3, 1, 1, 0, tzinfo=timezone.utc)  # 06:30 IST, 1 Mar
OBS_DATE = date(2026, 3, 1)
NOW = datetime(2026, 3, 1, 2, 0, tzinfo=timezone.utc)


def _obs(**overrides) -> FareObservation:
    raw = overrides.pop("raw", {"base_fare": 4000, "taxes": 200, "airport_charges": 620, "convenience_fee": 199, "total_fare": 5019, "currency": "INR"})
    base = FareObservation(
        source="DEMO_SIM",
        origin="DEL",
        destination="BOM",
        travel_date=OBS_DATE + timedelta(days=15),
        search_datetime=SEARCH,
        observation_date=OBS_DATE,
        lead_days=15,
        airline_code="6E",
        flight_number="6E123",
        cabin_class="ECONOMY",
        availability_status="AVAILABLE",
        fare=normalize_fare(raw),
    )
    return replace(base, **overrides)


def _statuses(results) -> set:
    return {r.status for r in results}


def test_clean_observation_without_reference_is_provisional():
    a = assess(_obs(), now=NOW)
    assert a.status == QualityStatus.PROVISIONAL
    assert "no_outlier_reference" in a.flags
    assert a.dedup_key


def test_clean_observation_with_reference_is_validated():
    ref = ReferenceStats(median_log_fare=math.log(5019), mad_log_fare=0.05, sample_size=40)
    a = assess(_obs(), QualityContext(reference_for=lambda r, l: ref), now=NOW)
    assert a.status == QualityStatus.VALIDATED
    assert a.score == 1.0
    assert a.robust_z == pytest.approx(0.0, abs=1e-6)


# --- required fields
def test_missing_required_fields_are_rejected():
    results = check_required_fields(_obs(origin=None, lead_days=None))
    assert _statuses(results) == {QualityStatus.REJECTED}
    assert {r.reason for r in results} == {"missing_required_field:origin", "missing_required_field:lead_days"}


# --- route
def test_same_origin_destination_rejected():
    assert _statuses(check_route(_obs(destination="DEL"))) == {QualityStatus.REJECTED}


def test_malformed_airport_code_rejected():
    assert _statuses(check_route(_obs(origin="DE1"))) == {QualityStatus.REJECTED}


def test_unknown_route_needs_review():
    results = check_route(_obs(origin="GOI", destination="IXZ"))
    assert _statuses(results) == {QualityStatus.REVIEW_REQUIRED}


# --- timestamps / dates
def test_future_search_timestamp_rejected():
    assert _statuses(check_search_timestamp(_obs(search_datetime=NOW + timedelta(hours=1)), now=NOW)) == {QualityStatus.REJECTED}


def test_naive_search_timestamp_rejected():
    assert _statuses(check_search_timestamp(_obs(search_datetime=datetime(2026, 3, 1, 1, 0)), now=NOW)) == {QualityStatus.REJECTED}


def test_travel_before_observation_rejected():
    assert _statuses(check_travel_date(_obs(travel_date=OBS_DATE - timedelta(days=1)))) == {QualityStatus.REJECTED}


def test_travel_too_far_ahead_rejected():
    assert _statuses(check_travel_date(_obs(travel_date=OBS_DATE + timedelta(days=400)))) == {QualityStatus.REJECTED}


# --- lead time
def test_unsupported_booking_window_rejected():
    assert _statuses(check_lead_time(_obs(lead_days=10, travel_date=OBS_DATE + timedelta(days=10)))) == {QualityStatus.REJECTED}


def test_declared_vs_actual_lead_time_mismatch_needs_review():
    assert _statuses(check_lead_time(_obs(lead_days=15, travel_date=OBS_DATE + timedelta(days=20)))) == {QualityStatus.REVIEW_REQUIRED}


def test_one_day_lead_time_slip_is_tolerated():
    assert check_lead_time(_obs(lead_days=15, travel_date=OBS_DATE + timedelta(days=16))) == []


# --- availability
@pytest.mark.parametrize("status, expected", [("SOLD_OUT", QualityStatus.SOLD_OUT), ("CANCELLED", QualityStatus.SOLD_OUT), ("NOT_FOUND", QualityStatus.MISSING), ("INVALID_QUOTE", QualityStatus.REJECTED)])
def test_availability_statuses(status, expected):
    assert _statuses(check_availability(_obs(availability_status=status))) == {expected}


def test_sold_out_observation_is_kept_as_sold_out_not_priced():
    a = assess(_obs(availability_status="SOLD_OUT", raw={"currency": "INR"}), now=NOW)
    assert a.status == QualityStatus.SOLD_OUT


# --- currency
def test_foreign_currency_needs_review_not_conversion():
    obs = _obs(raw={"total_fare": 60, "currency": "USD"})
    assert _statuses(check_currency(obs)) == {QualityStatus.REVIEW_REQUIRED}


def test_missing_currency_rejected():
    obs = _obs(raw={"total_fare": 5000})
    assert _statuses(check_currency(obs)) == {QualityStatus.REJECTED}


# --- fare value
def test_missing_total_on_available_is_missing():
    obs = _obs(raw={"base_fare": 4000, "taxes": 200, "currency": "INR"})
    assert _statuses(check_fare_value(obs)) == {QualityStatus.MISSING}
    assert assess(obs, now=NOW).status == QualityStatus.MISSING


def test_non_positive_fare_rejected():
    assert _statuses(check_fare_value(_obs(raw={"total_fare": 0, "currency": "INR"}))) == {QualityStatus.REJECTED}


@pytest.mark.parametrize("amount", [120, 900_000])
def test_implausible_fare_rejected(amount):
    assert _statuses(check_fare_value(_obs(raw={"total_fare": amount, "currency": "INR"}))) == {QualityStatus.REJECTED}


def test_unparseable_fare_rejected():
    assert QualityStatus.REJECTED in _statuses(check_fare_value(_obs(raw={"total_fare": "call us", "currency": "INR"})))


# --- components
def test_component_sum_mismatch_needs_review():
    obs = _obs(raw={"base_fare": 4000, "taxes": 900, "airport_charges": 620, "total_fare": 5019, "currency": "INR"})
    assert _statuses(check_fare_components(obs)) == {QualityStatus.REVIEW_REQUIRED}


def test_components_within_tolerance_pass():
    obs = _obs(raw={"base_fare": 4000, "taxes": 200, "airport_charges": 620, "convenience_fee": 199, "total_fare": 5040, "currency": "INR"})
    assert check_fare_components(obs) == []  # 21 INR off on 5040 < 1%


def test_negative_component_rejected():
    obs = _obs(raw={"base_fare": 4000, "taxes": -10, "total_fare": 3990, "currency": "INR"})
    assert _statuses(check_fare_components(obs)) == {QualityStatus.REJECTED}


def test_total_only_is_not_a_component_error_but_is_flagged():
    obs = _obs(raw={"total_fare": 5019, "currency": "INR"})
    assert check_fare_components(obs) == []
    assert "components_unavailable" in assess(obs, now=NOW).flags


# --- duplicates
def test_duplicate_detected_within_batch_and_nothing_dropped():
    tracker = DedupTracker()
    ctx = QualityContext(is_duplicate=tracker)
    first = assess(_obs(), ctx, now=NOW)
    second = assess(_obs(), ctx, now=NOW)
    assert first.status != QualityStatus.DUPLICATE
    assert second.status == QualityStatus.DUPLICATE


def test_duplicate_detected_against_existing_keys():
    key = compute_dedup_key(_obs())
    ctx = QualityContext(is_duplicate=DedupTracker({key}))
    assert assess(_obs(), ctx, now=NOW).status == QualityStatus.DUPLICATE


def test_dedup_key_ignores_fare_but_not_flight_or_day():
    assert compute_dedup_key(_obs()) == compute_dedup_key(_obs(raw={"total_fare": 9999, "currency": "INR"}))
    assert compute_dedup_key(_obs()) != compute_dedup_key(_obs(flight_number="6E999"))
    assert compute_dedup_key(_obs()) != compute_dedup_key(_obs(observation_date=OBS_DATE - timedelta(days=1)))


# --- outliers
def test_extreme_outlier_flagged_and_retained():
    ref = ReferenceStats(median_log_fare=math.log(5000), mad_log_fare=0.05, sample_size=40)
    obs = _obs(raw={"total_fare": 18000, "currency": "INR"})
    a = assess(obs, QualityContext(reference_for=lambda r, l: ref), now=NOW)
    assert a.status == QualityStatus.OUTLIER
    assert a.robust_z > 3.5


def test_small_reference_sample_makes_no_outlier_call():
    ref = ReferenceStats(median_log_fare=math.log(5000), mad_log_fare=0.05, sample_size=3)
    a = assess(_obs(raw={"total_fare": 18000, "currency": "INR"}), QualityContext(reference_for=lambda r, l: ref), now=NOW)
    assert a.status == QualityStatus.PROVISIONAL


def test_robust_statistics():
    ref = reference_from_log_fares([1.0, 2.0, 3.0, 4.0, 100.0])
    assert ref.median_log_fare == 3.0
    assert ref.mad_log_fare == 1.0
    assert robust_z_score(4.0, ref) == pytest.approx(0.6745)
    assert reference_from_log_fares([]) is None


# --- severity
def test_most_severe_status_wins_and_all_reasons_kept():
    # Unknown route (REVIEW_REQUIRED) + sold out (SOLD_OUT): SOLD_OUT is more severe.
    a = assess(_obs(origin="GOI", destination="IXZ", availability_status="SOLD_OUT", raw={"currency": "INR"}), now=NOW)
    assert a.status == QualityStatus.SOLD_OUT
    assert any(r.startswith("route_not_in_master") for r in a.reasons)

    # Implausible fare (REJECTED) on a duplicate (DUPLICATE): REJECTED wins, both reasons kept.
    obs = _obs(raw={"total_fare": 100, "currency": "INR"})
    a = assess(obs, QualityContext(is_duplicate=DedupTracker({compute_dedup_key(obs)})), now=NOW)
    assert a.status == QualityStatus.REJECTED
    assert "duplicate_of_earlier_observation" in a.reasons
    assert a.score == 0.0
