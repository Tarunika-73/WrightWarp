from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.enums import DataProvenance, QualityStatus
from app.core.lead_time import LEAD_TIME_DAYS
from app.core.routes import get_route, list_route_codes
from app.demo import market
from app.normalization.pipeline import ObservationContext, process_observation


def test_generation_is_deterministic_and_labelled():
    a = market.generate_observations("DEL-BOM", date(2025, 5, 1), 15)
    b = market.generate_observations("DEL-BOM", date(2025, 5, 1), 15)
    assert a == b
    assert a, "expected observations"
    for payload in a:
        assert payload["provenance"] == "SIMULATED"
        assert payload["data_label"] == "DEMO"
        assert payload["source"] == "DEMO_SIM"


def test_last_minute_fares_are_higher():
    assert market.lead_multiplier(1) > market.lead_multiplier(7) > market.lead_multiplier(30) > market.lead_multiplier(45)


def test_carriers_follow_route_master():
    carriers = {p["airline_code"] for p in market.generate_observations("BLR-HYD", date(2025, 3, 3), 30)}
    assert carriers <= set(get_route("BLR-HYD").demo_carriers)


def test_truth_relative_is_one_on_average_in_base_year():
    import math

    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(366)]
    mean_log = sum(math.log(market.true_route_relative("DEL-BOM", d, 2024)) for d in days) / len(days)
    assert mean_log == pytest.approx(0.0, abs=1e-9)


def test_unknown_route_yields_nothing():
    assert market.generate_observations("GOI-IXZ", date(2025, 1, 1), 1) == []


def test_backfill_dates_dense_recent_sparse_history():
    dates = market.backfill_dates(date(2024, 1, 1), date(2024, 12, 31), daily_recent_days=10, sparse_step=2)
    assert dates[-10:] == [date(2024, 12, 22) + timedelta(days=i) for i in range(10)]
    assert (dates[1] - dates[0]).days == 2


def test_simulated_payloads_pass_through_the_real_pipeline():
    statuses = set()
    for route in list_route_codes():
        o, d = route.split("-")
        for lead in LEAD_TIME_DAYS:
            for payload in market.generate_observations(route, date(2025, 8, 1), lead):
                ctx = ObservationContext(
                    search_run_id="r",
                    source="DEMO_SIM",
                    origin=o,
                    destination=d,
                    travel_date=date(2025, 8, 1) + timedelta(days=lead),
                    lead_days=lead,
                    search_datetime=datetime.fromisoformat(payload["observed_at"]),
                    provenance=DataProvenance.SIMULATED,
                )
                processed = process_observation(payload, ctx, now=datetime(2025, 8, 2, tzinfo=timezone.utc))
                statuses.add(processed.assessment.status)
                if processed.quote:
                    assert processed.quote.provenance == DataProvenance.SIMULATED.value
    assert QualityStatus.PROVISIONAL in statuses  # no reference distribution supplied
