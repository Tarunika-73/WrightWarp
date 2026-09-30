"""Simulated Indian domestic airfare market - DEMO DATA ONLY.

No real airline or OTA source has cleared compliance review yet (see
``app.core.sources``), so the demo runs on this simulator. It is a
statistical model, not a record of real prices, and everything it emits
is tagged ``provenance=SIMULATED`` / ``data_label=DEMO``.

Why a model with a known ground truth, rather than random numbers: the
backtest (``app.index_engine.backtest``) needs to know what the index
*should* have been in order to measure how well the pipeline recovers
it from noisy, gappy, partly corrupted observations. Every observed fare is

    fare = route_base x lead_multiplier(T+L) x airline_multiplier x F_route(d) x noise

where ``F_route(d)`` is the latent price level of the route on observation
day ``d`` (trend x seasonality x persistent route shock x common shock).
The true route index is ``F_route(d) / geomean(F_route over the base year)``,
exactly what an ideal Jevons elementary index would measure.

On top of that clean process the simulator injects the problems a real
collector meets, at fixed low rates: sold-out flights, missing totals,
fare-component mismatches, duplicated rows, gross outliers, total-only
payloads (no component breakdown), and whole-day gaps.

All randomness is derived from hashes of (route, date, ...), so the same
inputs always produce the same outputs, on any machine, in any order.

The parameters below are illustrative and hand-picked to look plausible.
They are NOT estimates from DGCA, MoSPI, or any airline.
"""
import hashlib
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache

from app.core.routes import get_route
from app.normalization.fares import IST

SIM_VERSION = "demo-market/1.0"
SIM_START = date(2024, 1, 1)
SIM_SOURCE_ID = "DEMO_SIM"


@dataclass(frozen=True)
class RouteParams:
    base_fare: float  # INR, economy, T+30-ish, average carrier, start of 2024
    annual_trend: float  # log growth per year
    shock_sigma: float  # daily sd of the persistent route shock (log)


ROUTE_PARAMS: dict[str, RouteParams] = {
    "DEL-BOM": RouteParams(5200.0, 0.060, 0.022),
    "DEL-BLR": RouteParams(6100.0, 0.075, 0.024),
    "BOM-BLR": RouteParams(3900.0, 0.050, 0.020),
    "DEL-CCU": RouteParams(5600.0, 0.085, 0.026),
    "BLR-HYD": RouteParams(3100.0, 0.040, 0.018),
    "MAA-DEL": RouteParams(6400.0, 0.070, 0.024),
}
DEFAULT_ROUTE_PARAMS = RouteParams(5000.0, 0.06, 0.022)

AIRLINE_MULTIPLIER: dict[str, float] = {"6E": 1.00, "AI": 1.10, "QP": 0.97, "SG": 0.95, "IX": 0.93}

# Fixed per-origin airport charges (UDF + passenger service fee), INR.
AIRPORT_CHARGES: dict[str, float] = {"DEL": 620.0, "BOM": 710.0, "BLR": 540.0, "CCU": 480.0, "HYD": 590.0, "MAA": 520.0}
CONVENIENCE_FEE = 199.0
GST_RATE_ON_BASE = 0.05

# Deterministic festival anchors (approximate Diwali dates) for seasonality.
_DIWALI = {2024: date(2024, 11, 1), 2025: date(2025, 10, 21), 2026: date(2026, 11, 8), 2027: date(2027, 10, 29)}

# Injection rates (probabilities per observation, except DAY_GAP per route/window/day).
P_DAY_GAP = 0.01
P_SOLD_OUT_BASE = 0.015
P_SOLD_OUT_T1 = 0.06
P_MISSING_TOTAL = 0.004
P_COMPONENT_MISMATCH = 0.004
P_DUPLICATE = 0.005
P_OUTLIER = 0.008
P_TOTAL_ONLY = 0.01
OBS_NOISE_SIGMA = 0.05

AR_ROUTE = 0.92
AR_COMMON = 0.97
COMMON_SHOCK_SIGMA = 0.008


def _seed(*parts: object) -> int:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _rng(*parts: object) -> random.Random:
    return random.Random(_seed(SIM_VERSION, *parts))


def lead_multiplier(lead_days: int) -> float:
    """Advance-purchase curve: last-minute fares are far higher, flattening beyond ~30 days."""
    return 0.90 + 0.95 * math.exp(-lead_days / 5.5)


def route_params(route: str) -> RouteParams:
    return ROUTE_PARAMS.get(route, DEFAULT_ROUTE_PARAMS)


def _bump(d: date, center: date, width_days: float) -> float:
    return math.exp(-(((d - center).days) / width_days) ** 2)


def seasonal_log(d: date) -> float:
    """Indian domestic travel seasonality on the observation date (log scale)."""
    y = d.year
    value = 0.0
    # Summer holidays (mid-May to June).
    value += 0.11 * _bump(d, date(y, 6, 1), 20)
    # Diwali / festive season.
    for year in (y - 1, y, y + 1):
        if year in _DIWALI:
            value += 0.16 * _bump(d, _DIWALI[year], 12)
    # Christmas - New Year.
    value += 0.13 * _bump(d, date(y, 12, 28), 9) + 0.13 * _bump(d, date(y - 1, 12, 28), 9)
    # Monsoon lull (mid-July to mid-September) and a February dip.
    value -= 0.07 * _bump(d, date(y, 8, 15), 25)
    value -= 0.04 * _bump(d, date(y, 2, 12), 12)
    return value


# route -> (route_shock, common_shock, combined path) extended incrementally, day by day from SIM_START.
_SHOCK_CACHE: dict[str, tuple[float, float, list[float]]] = {}


def _shock(route: str, d: date) -> float:
    """AR(1) route shock + AR(1) common shock on day ``d`` (0.0 before SIM_START)."""
    if d < SIM_START:
        return 0.0
    index = d.toordinal() - SIM_START.toordinal()
    params = route_params(route)
    route_shock, common, path = _SHOCK_CACHE.get(route, (0.0, 0.0, []))
    while len(path) <= index:
        day = SIM_START + timedelta(days=len(path))
        route_shock = AR_ROUTE * route_shock + _rng("route-shock", route, day).gauss(0.0, params.shock_sigma)
        common = AR_COMMON * common + _rng("common-shock", day).gauss(0.0, COMMON_SHOCK_SIGMA)
        path.append(route_shock + common)
    _SHOCK_CACHE[route] = (route_shock, common, path)
    return path[index]


def true_log_level(route: str, d: date) -> float:
    """log F_route(d): the latent (true) price level of a route on an observation day."""
    params = route_params(route)
    years = (d - SIM_START).days / 365.25
    return params.annual_trend * years + seasonal_log(d) + _shock(route, d)


def true_route_relative(route: str, d: date, base_year: int) -> float:
    """Ground-truth route index (base-year geometric mean = 1.0)."""
    return math.exp(true_log_level(route, d) - base_year_mean_log_level(route, base_year))


@lru_cache(maxsize=64)
def base_year_mean_log_level(route: str, base_year: int) -> float:
    start = date(base_year, 1, 1)
    days = (date(base_year + 1, 1, 1) - start).days
    return sum(true_log_level(route, start + timedelta(days=i)) for i in range(days)) / days


def true_mean_log_price(route: str, lead_days: int, carriers: tuple[str, ...], d: date) -> float:
    """Expected log fare (no noise) averaged over carriers - used for the backtest's price-level truth."""
    params = route_params(route)
    base = math.log(params.base_fare * lead_multiplier(lead_days))
    carrier_mean = sum(math.log(AIRLINE_MULTIPLIER.get(c, 1.0)) for c in carriers) / len(carriers)
    return base + carrier_mean + true_log_level(route, d)


def _flight_number(route: str, airline: str) -> str:
    return f"{airline}{100 + _seed('flight', route, airline) % 900}"


def _components(total: float, origin: str) -> dict[str, float]:
    airport = AIRPORT_CHARGES.get(origin, 550.0)
    base = round((total - airport - CONVENIENCE_FEE) / (1 + GST_RATE_ON_BASE), 2)
    taxes = round(total - airport - CONVENIENCE_FEE - base, 2)
    return {"base_fare": base, "taxes": taxes, "airport_charges": airport, "convenience_fee": CONVENIENCE_FEE}


def generate_observations(route: str, obs_date: date, lead_days: int) -> list[dict]:
    """Raw payloads the simulated market "shows" for one route/window on one observation day.

    Returns ``[]`` on a simulated whole-day gap. Payloads mimic what a
    scraper would extract (display strings are not used - the numbers are
    already parsed), and every one is labeled SIMULATED/DEMO.
    """
    definition = get_route(route)
    if definition is None:
        return []
    origin, destination = definition.origin, definition.destination
    if _rng("gap", route, lead_days, obs_date).random() < P_DAY_GAP:
        return []

    params = route_params(route)
    travel_date = obs_date + timedelta(days=lead_days)
    level = true_log_level(route, obs_date)
    search_base = datetime.combine(obs_date, time(6, 0), tzinfo=IST)

    payloads: list[dict] = []
    for index, airline in enumerate(definition.demo_carriers):
        rng = _rng("obs", route, lead_days, airline, obs_date)
        log_fare = (
            math.log(params.base_fare)
            + math.log(lead_multiplier(lead_days))
            + math.log(AIRLINE_MULTIPLIER.get(airline, 1.0))
            + level
            + rng.gauss(0.0, OBS_NOISE_SIGMA)
        )
        total = round(math.exp(log_fare), 0)
        payload: dict = {
            "provenance": "SIMULATED",
            "data_label": "DEMO",
            "simulator_version": SIM_VERSION,
            "source": SIM_SOURCE_ID,
            "airline_code": airline,
            "flight_number": _flight_number(route, airline),
            "origin": origin,
            "destination": destination,
            "travel_date": travel_date.isoformat(),
            "lead_days": lead_days,
            "cabin_class": "ECONOMY",
            "stops": 0,
            "currency": "INR",
            "availability_status": "AVAILABLE",
            "observed_at": (search_base + timedelta(minutes=7 * index + 3 * (lead_days % 7))).isoformat(),
        }

        p_sold_out = P_SOLD_OUT_T1 if lead_days <= 1 else P_SOLD_OUT_BASE
        roll = rng.random()
        if roll < p_sold_out:
            payload["availability_status"] = "SOLD_OUT"
            payloads.append(payload)
            continue
        roll -= p_sold_out

        if roll < P_OUTLIER:
            # Gross error (e.g. a business-class fare leaking into economy, or a stale cached price).
            total = round(total * (rng.uniform(2.8, 4.0) if rng.random() < 0.7 else rng.uniform(0.22, 0.3)), 0)
        roll -= P_OUTLIER

        components = _components(total, origin)
        if roll < P_TOTAL_ONLY:
            payload["total_fare"] = total  # source shows only a total
        elif roll < P_TOTAL_ONLY + P_MISSING_TOTAL:
            payload.update(components)  # components but no total
        elif roll < P_TOTAL_ONLY + P_MISSING_TOTAL + P_COMPONENT_MISMATCH:
            components["taxes"] = round(components["taxes"] + rng.uniform(300, 900), 2)
            payload.update(components)
            payload["total_fare"] = total
        else:
            payload.update(components)
            payload["total_fare"] = total
        payloads.append(payload)

        if rng.random() < P_DUPLICATE:
            payloads.append(dict(payload))
    return payloads


def backfill_dates(start: date, end: date, *, daily_recent_days: int = 120, sparse_step: int = 2) -> list[date]:
    """Observation days for the historical demo backfill.

    Daily for the most recent ``daily_recent_days`` (what the daily chart
    shows), every ``sparse_step`` days before that - enough for stable
    weekly/monthly indices while keeping the demo database small.
    """
    dense_from = end - timedelta(days=daily_recent_days - 1)
    dates = []
    d = start
    while d <= end:
        if d >= dense_from or (d - start).days % sparse_step == 0:
            dates.append(d)
        d += timedelta(days=1)
    return dates
