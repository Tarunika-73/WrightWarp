"""Backtesting: compare computed index series against reference series.

Two kinds of reference are supported:

* ``SimulatorTruth`` - the known latent price process of the demo market
  (``app.demo.market``). Comparing against it measures how well the whole
  pipeline (quality engine + normalization + index formulas) *recovers* a
  known index from noisy, gappy, partly corrupted observations. It is a
  simulation study, labeled "DEMO DATA - NOT OFFICIAL". It says nothing
  about how the index compares to official statistics.
* Stored reference series (``reference_series`` collection) - e.g. an
  official CPI airfare sub-index, once someone loads one. None is
  shipped: no official series is fabricated here.

Metrics (per matched period): MAE, RMSE, MAPE (index values are strictly
positive and near 100, so MAPE is well defined), mean error (bias),
maximum absolute error, Pearson correlation, and stability - the standard
deviation of period-on-period % changes of both series, and how often
they move in the same direction.
"""
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from app.core.routes import get_route
from app.demo import market
from app.index_engine.calculators import CALCULATORS, ElementaryAggregate, WeightContext
from app.index_engine.engine import BASE_INDEX_VALUE, SeriesResult
from app.index_engine.periods import Frequency, period_key, period_start
from app.index_engine.weights import WeightSet

BACKTEST_VERSION = "backtest/1.0"


@dataclass(frozen=True)
class Metrics:
    n_periods: int
    mae: float
    rmse: float
    mape_pct: float
    bias: float
    max_abs_error: float
    correlation: float | None
    est_change_sd_pct: float | None
    ref_change_sd_pct: float | None
    direction_agreement_pct: float | None

    def as_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


def _changes(values: list[float]) -> list[float]:
    return [(b / a - 1) * 100 for a, b in zip(values, values[1:]) if a > 0]


def _sd(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    m = sum(values) / len(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def _corr(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def compare_series(estimated: dict[str, float], reference: dict[str, float]) -> Metrics | None:
    """Metrics over the periods present in both series (keys are period strings)."""
    periods = sorted(set(estimated) & set(reference))
    if not periods:
        return None
    est = [estimated[p] for p in periods]
    ref = [reference[p] for p in periods]
    errors = [e - r for e, r in zip(est, ref)]
    est_changes, ref_changes = _changes(est), _changes(ref)
    agreement = None
    if est_changes:
        same = sum(1 for a, b in zip(est_changes, ref_changes) if (a >= 0) == (b >= 0))
        agreement = 100.0 * same / len(est_changes)
    return Metrics(
        n_periods=len(periods),
        mae=sum(abs(e) for e in errors) / len(errors),
        rmse=math.sqrt(sum(e * e for e in errors) / len(errors)),
        mape_pct=100.0 * sum(abs(e) / r for e, r in zip(errors, ref)) / len(errors),
        bias=sum(errors) / len(errors),
        max_abs_error=max(abs(e) for e in errors),
        correlation=_corr(est, ref),
        est_change_sd_pct=_sd(est_changes),
        ref_change_sd_pct=_sd(ref_changes),
        direction_agreement_pct=agreement,
    )


class SimulatorTruth:
    """Ground-truth index series of the demo market, on the same observation days as the data."""

    reference_id = "DEMO_SIM_TRUTH"
    label = "DEMO DATA - simulator ground truth, NOT OFFICIAL"

    def __init__(self, *, base_year: int, weight_set: WeightSet, observation_dates: list[date], windows: list[int]):
        self.base_year = base_year
        self.weight_set = weight_set
        self.dates = sorted(set(observation_dates))
        self.windows = windows

    def _route_p0(self, route: str, leads: list[int]) -> float:
        definition = get_route(route)
        carriers = definition.demo_carriers if definition else ("6E",)
        base_level = market.base_year_mean_log_level(route, self.base_year)
        logs = [
            market.true_mean_log_price(route, lead, carriers, date(self.base_year, 1, 1))
            - market.true_log_level(route, date(self.base_year, 1, 1))
            + base_level
            for lead in leads
        ]
        return math.exp(sum(logs) / len(logs))

    def route_relatives(self, route: str, frequency: Frequency) -> dict[str, float]:
        """True relative per period: geometric mean of the daily true relatives on observed days."""
        base = market.base_year_mean_log_level(route, self.base_year)
        acc: dict[str, list[float]] = defaultdict(list)
        for d in self.dates:
            acc[period_key(d, frequency)].append(market.true_log_level(route, d) - base)
        return {p: math.exp(sum(v) / len(v)) for p, v in acc.items()}

    def series(self, routes: list[str], frequency: Frequency, method: str, lead: int | None = None) -> dict[str, float]:
        """Truth for the overall index (lead=None) or one booking window, with the given formula."""
        leads = self.windows if lead is None else [lead]
        relatives = {r: self.route_relatives(r, frequency) for r in routes}
        p0 = {r: self._route_p0(r, leads) for r in routes}
        base_q, _ = self.weight_set.quantities_for(self.base_year, fallback_year=self.base_year)
        calc = CALCULATORS[method]
        out: dict[str, float] = {}
        for period in sorted(set().union(*(set(v) for v in relatives.values()))):
            aggs = [ElementaryAggregate(r, relatives[r][period], p0[r]) for r in routes if period in relatives[r] and r in base_q]
            if not aggs:
                continue
            year = period_start(period, frequency).year
            current_q, _ = self.weight_set.quantities_for(year, fallback_year=self.base_year)
            out[period] = BASE_INDEX_VALUE * calc.calculate(aggs, WeightContext(base_q, current_q))
        return out


def _values(series: SeriesResult) -> dict[str, float]:
    return {p["period"]: p["value"] for p in series.points}


def run_simulator_backtest(
    series: list[SeriesResult],
    truth: SimulatorTruth,
    *,
    routes: list[str],
    default_method: str,
    exclude_base_year: bool = True,
) -> dict:
    """Full backtest report (JSON-serialisable) of computed series vs simulator truth.

    By default the base year itself is excluded from the metrics: inside
    the base year the index is anchored to its own data, which would
    flatter the error statistics.
    """
    by_id = {s.series_id: s for s in series}

    def keep(values: dict[str, float], frequency: Frequency) -> dict[str, float]:
        if not exclude_base_year:
            return values
        return {p: v for p, v in values.items() if period_start(p, frequency).year != truth.base_year}

    report: dict = {"methodologies": {}, "routes": {}, "windows": {}, "series": {}}
    for method in CALCULATORS:
        report["methodologies"][method] = {}
        for frequency in Frequency:
            s = by_id.get(f"{method}:{frequency.value}:overall:ALL")
            if s is None:
                continue
            ref = truth.series(routes, frequency, method)
            m = compare_series(keep(_values(s), frequency), keep(ref, frequency))
            report["methodologies"][method][frequency.value] = m.as_dict() if m else None
            if frequency == Frequency.MONTHLY:
                report["series"][method] = [
                    {"period": p, "estimated": round(v, 3), "reference": round(ref[p], 3)}
                    for p, v in sorted(_values(s).items())
                    if p in ref
                ]

    for route in routes:
        report["routes"][route] = {}
        for frequency in (Frequency.WEEKLY, Frequency.MONTHLY):
            s = by_id.get(f"ELEMENTARY_JEVONS:{frequency.value}:route:{route}")
            if s is None:
                continue
            ref = {p: BASE_INDEX_VALUE * v for p, v in truth.route_relatives(route, frequency).items()}
            m = compare_series(keep(_values(s), frequency), keep(ref, frequency))
            report["routes"][route][frequency.value] = m.as_dict() if m else None

    for lead in truth.windows:
        s = by_id.get(f"{default_method}:{Frequency.MONTHLY.value}:window:T+{lead}")
        if s is None:
            continue
        ref = truth.series(routes, Frequency.MONTHLY, default_method, lead=lead)
        m = compare_series(keep(_values(s), Frequency.MONTHLY), keep(ref, Frequency.MONTHLY))
        report["windows"][f"T+{lead}"] = {"monthly": m.as_dict() if m else None}

    report["methodology_comparison"] = methodology_comparison(series)
    return report


def methodology_comparison(series: list[SeriesResult]) -> dict:
    """How far apart the formulas are, per frequency (no reference needed)."""
    out: dict = {}
    for frequency in Frequency:
        values = {
            s.methodology: _values(s)
            for s in series
            if s.scope == "overall" and s.frequency == frequency and s.methodology in CALCULATORS
        }
        if not values:
            continue
        periods = sorted(set.intersection(*(set(v) for v in values.values())))
        if not periods:
            continue
        spreads = [max(v[p] for v in values.values()) - min(v[p] for v in values.values()) for p in periods]
        out[frequency.value] = {
            "n_periods": len(periods),
            "mean_spread_points": round(sum(spreads) / len(spreads), 4),
            "max_spread_points": round(max(spreads), 4),
            "latest": {m: round(v[periods[-1]], 3) for m, v in values.items()},
            "latest_period": periods[-1],
        }
    return out
