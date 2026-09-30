"""Pure index computation: daily elementary cells in, index series out.

No database access - ``app.index_engine.service`` loads cells from
MongoDB, calls ``compute_series``, and stores the result. That split keeps
every number here reproducible from its inputs and unit-testable.

Definitions (see docs/INDEX_METHODOLOGY.md):

* **Cell**: one (observation day, route, booking window, carrier) with the
  mean log total fare of its index-eligible observations.
* **Item**: (route, booking window, carrier). Its base price is the
  geometric mean of its daily cell prices over the base year.
* **Period price** of an item: geometric mean of its daily cell prices in
  the period (day / ISO week / month).
* **Route relative** (elementary, Jevons): geometric mean over the route's
  matched items (items with both a base and a period price) of
  period price / base price. Items without a base-year price are excluded
  (reported as ``unmatched_items``) - they cannot be compared to base.
* **Route base price** P0: geometric mean of the route's item base prices.
* **Upper level**: ``IndexCalculator`` over route relatives with route weights.
"""
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from app.index_engine.calculators import (
    CALCULATORS,
    ElementaryAggregate,
    IndexCalculationError,
    WeightContext,
)
from app.index_engine.periods import Frequency, period_key, period_start
from app.index_engine.weights import WeightSet

CALCULATION_VERSION = "index-engine/1.0"
ELEMENTARY_METHOD = "ELEMENTARY_JEVONS"
BASE_INDEX_VALUE = 100.0


@dataclass(frozen=True)
class Cell:
    date: date
    route: str
    lead_days: int
    airline: str
    mean_log_fare: float
    n_obs: int


Item = tuple[str, int, str]  # (route, lead_days, airline)


@dataclass
class SeriesResult:
    methodology: str
    frequency: Frequency
    scope: str  # overall | window | route | route_window
    scope_key: str  # "ALL" | "T+15" | "DEL-BOM" | "DEL-BOM|T+15"
    points: list[dict] = field(default_factory=list)

    @property
    def series_id(self) -> str:
        return f"{self.methodology}:{self.frequency.value}:{self.scope}:{self.scope_key}"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def base_prices(cells: list[Cell], base_year: int) -> dict[Item, float]:
    """Mean log price per item over the base year."""
    acc: dict[Item, list[float]] = defaultdict(list)
    for c in cells:
        if c.date.year == base_year:
            acc[(c.route, c.lead_days, c.airline)].append(c.mean_log_fare)
    return {item: _mean(v) for item, v in acc.items()}


def _period_prices(cells: list[Cell], frequency: Frequency) -> dict[str, dict[Item, tuple[float, int]]]:
    acc: dict[str, dict[Item, list]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0, 0]))
    for c in cells:
        slot = acc[period_key(c.date, frequency)][(c.route, c.lead_days, c.airline)]
        slot[0] += c.mean_log_fare
        slot[1] += 1  # days
        slot[2] += c.n_obs
    return {p: {item: (s[0] / s[1], s[2]) for item, s in items.items()} for p, items in acc.items()}


def _elementary(
    period_items: dict[Item, tuple[float, int]],
    base: dict[Item, float],
    group_of,
) -> dict[object, tuple[float, int, int]]:
    """Group matched items and return {group: (relative, n_items, n_obs)}."""
    diffs: dict[object, list[float]] = defaultdict(list)
    obs: dict[object, int] = defaultdict(int)
    for item, (log_price, n_obs) in period_items.items():
        if item not in base:
            continue
        g = group_of(item)
        diffs[g].append(log_price - base[item])
        obs[g] += n_obs
    return {g: (math.exp(_mean(d)), len(d), obs[g]) for g, d in diffs.items()}


def compute_series(
    cells: list[Cell],
    *,
    base_year: int,
    weight_set: WeightSet,
    frequencies: tuple[Frequency, ...] = (Frequency.DAILY, Frequency.WEEKLY, Frequency.MONTHLY),
    methodologies: tuple[str, ...] | None = None,
) -> list[SeriesResult]:
    methodologies = methodologies or tuple(CALCULATORS)
    base = base_prices(cells, base_year)
    if not base:
        raise IndexCalculationError(f"no observations in base year {base_year}; cannot anchor the index")

    route_base_log: dict[str, list[float]] = defaultdict(list)
    route_window_base_log: dict[tuple[str, int], list[float]] = defaultdict(list)
    for (route, lead, _airline), value in base.items():
        route_base_log[route].append(value)
        route_window_base_log[(route, lead)].append(value)
    route_p0 = {r: math.exp(_mean(v)) for r, v in route_base_log.items()}
    route_window_p0 = {k: math.exp(_mean(v)) for k, v in route_window_base_log.items()}
    windows = sorted({lead for (_r, lead) in route_window_p0})
    base_q, _ = weight_set.quantities_for(base_year, fallback_year=base_year)

    results: dict[str, SeriesResult] = {}

    def series(method: str, freq: Frequency, scope: str, key: str) -> SeriesResult:
        s = SeriesResult(method, freq, scope, key)
        return results.setdefault(s.series_id, s)

    for frequency in frequencies:
        by_period = _period_prices(cells, frequency)
        for period in sorted(by_period):
            items = by_period[period]
            year = period_start(period, frequency).year
            current_q, weight_year = weight_set.quantities_for(year, fallback_year=base_year)
            weights = WeightContext(base_quantities=base_q, current_quantities=current_q)

            routes = _elementary(items, base, lambda it: it[0])
            route_windows = _elementary(items, base, lambda it: (it[0], it[1]))
            unmatched = sum(1 for it in items if it not in base)
            total_obs = sum(n for _p, n in items.values())

            for route, (rel, n_items, n_obs) in routes.items():
                series(ELEMENTARY_METHOD, frequency, "route", route).points.append(
                    _point(period, frequency, rel, n_obs=n_obs, n_items=n_items, price=route_p0[route] * rel)
                )
            for (route, lead), (rel, n_items, n_obs) in route_windows.items():
                series(ELEMENTARY_METHOD, frequency, "route_window", f"{route}|T+{lead}").points.append(
                    _point(period, frequency, rel, n_obs=n_obs, n_items=n_items, price=route_window_p0[(route, lead)] * rel)
                )

            overall_aggs = [
                ElementaryAggregate(r, rel, route_p0[r], n_items, n_obs) for r, (rel, n_items, n_obs) in routes.items() if r in base_q
            ]
            window_aggs = {
                lead: [
                    ElementaryAggregate(r, rel, route_window_p0[(r, l)], n_items, n_obs)
                    for (r, l), (rel, n_items, n_obs) in route_windows.items()
                    if l == lead and r in base_q
                ]
                for lead in windows
            }
            for method in methodologies:
                calc = CALCULATORS[method]
                if overall_aggs:
                    value = calc.calculate(overall_aggs, weights)
                    series(method, frequency, "overall", "ALL").points.append(
                        _point(
                            period,
                            frequency,
                            value,
                            n_obs=total_obs,
                            n_items=sum(a.n_items for a in overall_aggs),
                            n_routes=len(overall_aggs),
                            unmatched_items=unmatched,
                            weight_year=weight_year,
                        )
                    )
                for lead, aggs in window_aggs.items():
                    if not aggs:
                        continue
                    value = calc.calculate(aggs, weights)
                    series(method, frequency, "window", f"T+{lead}").points.append(
                        _point(
                            period,
                            frequency,
                            value,
                            n_obs=sum(a.n_obs for a in aggs),
                            n_items=sum(a.n_items for a in aggs),
                            n_routes=len(aggs),
                            weight_year=weight_year,
                        )
                    )
    return list(results.values())


def _point(period: str, frequency: Frequency, relative: float, **extra) -> dict:
    point = {
        "period": period,
        "start": period_start(period, frequency).isoformat(),
        "value": round(relative * BASE_INDEX_VALUE, 4),
    }
    if extra.get("price") is not None:
        extra["price"] = round(extra["price"], 2)
    point.update({k: v for k, v in extra.items() if v is not None})
    return point
