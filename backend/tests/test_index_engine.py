"""Index engine on hand-built cells with known answers."""
import math
from datetime import date, timedelta

import pytest

from app.index_engine.calculators import IndexCalculationError
from app.index_engine.engine import ELEMENTARY_METHOD, Cell, base_prices, compute_series
from app.index_engine.periods import Frequency, period_end, period_key, period_start
from app.index_engine.weights import parse_weight_set


def _weights():
    routes = ["DEL-BOM", "DEL-BLR", "BOM-BLR", "DEL-CCU", "BLR-HYD", "MAA-DEL"]
    payload = {
        "version": "TEST-1",
        "label": "DEMO",
        "source": "unit test",
        "quantities": {"2024": {r: 1.0 for r in routes}, "2025": {r: 1.0 for r in routes}},
    }
    return parse_weight_set(payload, base_year=2024, file_name="t.json", raw_bytes=b"x")


def _cells(route, lead, airline, start, days, price_fn):
    return [Cell(start + timedelta(days=i), route, lead, airline, math.log(price_fn(start + timedelta(days=i))), 1) for i in range(days)]


def _by_id(series):
    return {s.series_id: s for s in series}


def test_constant_prices_give_index_100_everywhere():
    cells = _cells("DEL-BOM", 15, "6E", date(2024, 1, 1), 400, lambda d: 5000.0)
    cells += _cells("DEL-BLR", 15, "AI", date(2024, 1, 1), 400, lambda d: 6000.0)
    series = compute_series(cells, base_year=2024, weight_set=_weights())
    for s in series:
        for p in s.points:
            assert p["value"] == pytest.approx(100.0)


def test_price_doubling_after_base_year_gives_200():
    price = lambda d: 4000.0 if d.year == 2024 else 8000.0
    cells = _cells("DEL-BOM", 7, "6E", date(2024, 1, 1), 500, price)
    by = _by_id(compute_series(cells, base_year=2024, weight_set=_weights()))
    monthly = by["LASPEYRES:monthly:overall:ALL"].points
    assert monthly[0]["value"] == pytest.approx(100.0)
    assert monthly[-1]["value"] == pytest.approx(200.0)
    route = by[f"{ELEMENTARY_METHOD}:monthly:route:DEL-BOM"].points
    assert route[-1]["value"] == pytest.approx(200.0)
    assert route[-1]["price"] == pytest.approx(8000.0)


def test_route_relative_is_geometric_mean_of_item_relatives():
    start = date(2024, 1, 1)
    cells = _cells("DEL-BOM", 1, "6E", start, 366, lambda d: 1000.0)
    cells += _cells("DEL-BOM", 30, "AI", start, 366, lambda d: 2000.0)
    # 2025-01-01: 6E up 21%, AI down 10%.
    cells.append(Cell(date(2025, 1, 1), "DEL-BOM", 1, "6E", math.log(1210.0), 1))
    cells.append(Cell(date(2025, 1, 1), "DEL-BOM", 30, "AI", math.log(1800.0), 1))
    by = _by_id(compute_series(cells, base_year=2024, weight_set=_weights(), frequencies=(Frequency.DAILY,)))
    point = by[f"{ELEMENTARY_METHOD}:daily:route:DEL-BOM"].points[-1]
    assert point["period"] == "2025-01-01"
    assert point["value"] == pytest.approx(100 * math.sqrt(1.21 * 0.9))
    assert point["n_items"] == 2


def test_items_without_base_price_are_excluded_and_counted():
    cells = _cells("DEL-BOM", 15, "6E", date(2024, 1, 1), 370, lambda d: 5000.0)
    cells.append(Cell(date(2025, 1, 2), "DEL-BOM", 15, "QP", math.log(99999.0), 1))  # new carrier, no base
    by = _by_id(compute_series(cells, base_year=2024, weight_set=_weights(), frequencies=(Frequency.DAILY,)))
    point = next(p for p in by["LASPEYRES:daily:overall:ALL"].points if p["period"] == "2025-01-02")
    assert point["value"] == pytest.approx(100.0)  # the new carrier's fare does not move the index
    assert point["unmatched_items"] == 1


def test_window_and_route_window_series_exist():
    cells = _cells("DEL-BOM", 1, "6E", date(2024, 1, 1), 40, lambda d: 9000.0)
    cells += _cells("DEL-BOM", 45, "6E", date(2024, 1, 1), 40, lambda d: 4000.0)
    by = _by_id(compute_series(cells, base_year=2024, weight_set=_weights()))
    assert "LASPEYRES:weekly:window:T+1" in by
    assert "FISHER:monthly:window:T+45" in by
    assert f"{ELEMENTARY_METHOD}:daily:route_window:DEL-BOM|T+1" in by


def test_no_base_year_data_is_an_error():
    cells = _cells("DEL-BOM", 1, "6E", date(2025, 1, 1), 10, lambda d: 9000.0)
    with pytest.raises(IndexCalculationError):
        compute_series(cells, base_year=2024, weight_set=_weights())


def test_base_prices_are_base_year_log_means():
    cells = [Cell(date(2024, 1, 1), "DEL-BOM", 1, "6E", 1.0, 1), Cell(date(2024, 6, 1), "DEL-BOM", 1, "6E", 3.0, 1), Cell(date(2025, 1, 1), "DEL-BOM", 1, "6E", 99.0, 1)]
    assert base_prices(cells, 2024) == {("DEL-BOM", 1, "6E"): 2.0}


@pytest.mark.parametrize(
    "d, freq, key, start, end",
    [
        (date(2026, 9, 30), Frequency.DAILY, "2026-09-30", date(2026, 9, 30), date(2026, 9, 30)),
        (date(2026, 9, 30), Frequency.WEEKLY, "2026-W40", date(2026, 9, 28), date(2026, 10, 4)),
        (date(2024, 12, 30), Frequency.WEEKLY, "2025-W01", date(2024, 12, 30), date(2025, 1, 5)),
        (date(2024, 2, 10), Frequency.MONTHLY, "2024-02", date(2024, 2, 1), date(2024, 2, 29)),
        (date(2025, 12, 31), Frequency.MONTHLY, "2025-12", date(2025, 12, 1), date(2025, 12, 31)),
    ],
)
def test_period_keys(d, freq, key, start, end):
    assert period_key(d, freq) == key
    assert period_start(key, freq) == start
    assert period_end(key, freq) == end
