import math
from datetime import date, timedelta

import pytest

from app.core.lead_time import LEAD_TIME_DAYS, parse_window_days
from app.core.routes import list_route_codes
from app.index_engine.backtest import SimulatorTruth, compare_series, methodology_comparison, run_simulator_backtest
from app.index_engine.engine import Cell, compute_series
from app.index_engine.weights import (
    WeightValidationError,
    active_weight_set,
    load_weight_sets,
    parse_weight_set,
    validate_weight_payload,
)

ROUTES = list(list_route_codes())


def _payload(**overrides):
    payload = {"version": "X", "label": "DEMO", "source": "test", "quantities": {"2024": {r: 1.0 for r in ROUTES}}}
    payload.update(overrides)
    return payload


def test_shipped_weight_set_is_labelled_demo_and_valid():
    ws = active_weight_set(2024)
    assert ws.label == "DEMO"
    assert ws.is_official is False
    assert "NOT DGCA" in ws.source
    assert set(ws.quantities[2024]) == set(ROUTES)
    assert sum(ws.shares(2024).values()) == pytest.approx(1.0)
    assert len(ws.checksum) == 64


def test_demo_set_can_never_claim_to_be_official():
    with pytest.raises(WeightValidationError):
        validate_weight_payload(_payload(is_official=True), base_year=2024)
    with pytest.raises(WeightValidationError):
        validate_weight_payload(_payload(label="OFFICIAL"), base_year=2024)


@pytest.mark.parametrize(
    "quantities",
    [
        {"2025": {r: 1.0 for r in ROUTES}},  # no base year
        {"2024": {**{r: 1.0 for r in ROUTES}, "GOI-IXZ": 1.0}},  # unknown route
        {"2024": {**{r: 1.0 for r in ROUTES}, "DEL-BOM": 0}},  # non-positive
        {"2024": {r: 1.0 for r in ROUTES[:-1]}},  # missing route in base year
    ],
)
def test_invalid_weight_sets_rejected(quantities):
    with pytest.raises(WeightValidationError):
        validate_weight_payload(_payload(quantities=quantities), base_year=2024)


def test_official_set_preferred_over_demo(tmp_path, monkeypatch):
    import json

    (tmp_path / "a.json").write_text(json.dumps(_payload(version="DEMO-9")))
    (tmp_path / "b.json").write_text(json.dumps(_payload(version="DGCA-1", label="OFFICIAL", is_official=True)))
    sets = load_weight_sets(2024, str(tmp_path))
    official = [s for s in sets if s.is_official]
    assert [s.version for s in official] == ["DGCA-1"]


def test_quantities_fall_back_to_latest_earlier_year():
    ws = parse_weight_set(_payload(quantities={"2024": {r: 1.0 for r in ROUTES}, "2025": {r: 2.0 for r in ROUTES}}), base_year=2024, file_name="x", raw_bytes=b"")
    q, year = ws.quantities_for(2027, fallback_year=2024)
    assert year == 2025 and q["DEL-BOM"] == 2.0


def test_booking_windows_configurable():
    assert parse_window_days(None) == (1, 7, 15, 30, 45)
    assert parse_window_days("45, 1,7") == (1, 7, 45)
    with pytest.raises(ValueError):
        parse_window_days("1,999")


def test_compare_series_metrics():
    est = {"a": 101.0, "b": 99.0, "c": 102.0}
    ref = {"a": 100.0, "b": 100.0, "c": 100.0, "d": 100.0}
    m = compare_series(est, ref)
    assert m.n_periods == 3
    assert m.mae == pytest.approx(4 / 3)
    assert m.rmse == pytest.approx(math.sqrt((1 + 1 + 4) / 3))
    assert m.mape_pct == pytest.approx(4 / 3)
    assert m.bias == pytest.approx(2 / 3)
    assert m.max_abs_error == pytest.approx(2.0)
    assert compare_series({"x": 1.0}, {"y": 1.0}) is None


def test_simulator_backtest_recovers_truth_on_clean_cells():
    """With noise-free cells generated from the simulator's own truth, errors must be ~0."""
    from app.demo import market

    ws = active_weight_set(2024)
    # Every base-year day (the truth's base is the full-year geometric mean),
    # sparser afterwards. Sparse base-year sampling is a genuine error source
    # that the real backtest is supposed to measure, so it is excluded here.
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(366)]
    days += [date(2025, 1, 1) + timedelta(days=i) for i in range(0, 300, 5)]
    cells = []
    from app.core.routes import get_route

    for route in ROUTES:
        for airline in get_route(route).demo_carriers:
            for lead in LEAD_TIME_DAYS:
                for d in days:
                    cells.append(Cell(d, route, lead, airline, market.true_mean_log_price(route, lead, (airline,), d), 1))
    series = compute_series(cells, base_year=2024, weight_set=ws)
    truth = SimulatorTruth(base_year=2024, weight_set=ws, observation_dates=days, windows=list(LEAD_TIME_DAYS))
    report = run_simulator_backtest(series, truth, routes=ROUTES, default_method="LASPEYRES")
    for method, by_freq in report["methodologies"].items():
        assert by_freq["monthly"]["mae"] < 0.01, method
    assert report["routes"]["DEL-BOM"]["monthly"]["mae"] < 0.01
    assert "monthly" in methodology_comparison(series)
