"""Fare observation endpoints: normalized quotes, provenance trace, booking-window analysis.

Answers the core SIH26056 question directly: *"what is the airfare for a
route when the ticket is purchased X days before travel?"* -
``GET /fares/booking-window?route=DEL-BOM&travel_date=YYYY-MM-DD`` returns,
for every configured window T+X, the fares observed X days before that
travel date.
"""
import math
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import Pagination, get_db
from app.core.enums import INDEX_ELIGIBLE_QUALITY, QualityStatus
from app.core.errors import AppError, NotFoundError
from app.core.lead_time import LEAD_TIME_DAYS, window_name
from app.core.routes import RouteDefinition, get_route
from app.db.bson_utils import date_to_datetime, datetime_to_date
from app.repositories.flight_quote_repository import FlightQuoteRepository
from app.repositories.raw_observation_repository import RawObservationRepository
from app.repositories.search_run_repository import SearchRunRepository
from app.schemas.analytics import BookingWindowFare
from app.schemas.flight_quote import FlightQuoteRead

router = APIRouter(tags=["fares"])

MAX_RANGE_DAYS = 400


def _route_or_404(route: str) -> RouteDefinition:
    definition = get_route(route)
    if definition is None:
        raise NotFoundError(f"Route {route!r} is not a monitored route")
    return definition


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _fare_stats(quotes: list[FlightQuoteRead]) -> dict:
    valid = [q for q in quotes if q.quality_status in INDEX_ELIGIBLE_QUALITY and q.total_fare]
    fares = [q.total_fare for q in valid]
    by_airline: dict[str, list[float]] = {}
    for q in valid:
        by_airline.setdefault(q.airline_code or "UNKNOWN", []).append(q.total_fare)
    return {
        "observations": len(quotes),
        "valid_observations": len(valid),
        "min_fare": min(fares) if fares else None,
        "median_fare": _median(fares),
        "geometric_mean_fare": round(math.exp(sum(math.log(f) for f in fares) / len(fares)), 2) if fares else None,
        "max_fare": max(fares) if fares else None,
        "by_airline": [{"airline_code": a, "fares": v, "min_fare": min(v)} for a, v in sorted(by_airline.items())],
    }


def _quote_query(
    definition: RouteDefinition | None,
    *,
    travel_date: date | None = None,
    lead_days: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    source: str | None = None,
    quality_status: QualityStatus | None = None,
    airline: str | None = None,
) -> dict:
    query: dict = {}
    if definition:
        query["route.origin"] = definition.origin
        query["route.destination"] = definition.destination
    if travel_date:
        query["travel.travel_date"] = date_to_datetime(travel_date)
    if lead_days is not None:
        query["travel.lead_days"] = lead_days
    if date_from or date_to:
        rng = {}
        if date_from:
            rng["$gte"] = date_to_datetime(date_from)
        if date_to:
            rng["$lte"] = date_to_datetime(date_to)
        query["travel.observation_date"] = rng
    if source:
        query["source.id"] = source
    if quality_status:
        query["quality.status"] = quality_status.value
    if airline:
        query["flight.airline_code"] = airline.upper()
    return query


async def _list_quotes(db, pagination: Pagination, **filters) -> dict:
    route = filters.pop("route", None)
    definition = _route_or_404(route) if route else None
    query = _quote_query(definition, **filters)
    repo = FlightQuoteRepository(db)
    total = await repo.count(query)
    items = await repo.search(query, skip=pagination.skip, limit=pagination.page_size)
    return {
        "items": items,
        "page": {"page": pagination.page, "page_size": pagination.page_size, "total": total, "pages": math.ceil(total / pagination.page_size) if total else 0},
    }


def _filters(
    route: str | None = Query(None, description="Route code, e.g. DEL-BOM"),
    travel_date: date | None = Query(None),
    lead_days: int | None = Query(None, description="Booking window in days (T+N)"),
    date_from: date | None = Query(None, description="Observation date from (IST, inclusive)"),
    date_to: date | None = Query(None, description="Observation date to (IST, inclusive)"),
    source: str | None = Query(None),
    quality_status: QualityStatus | None = Query(None),
    airline: str | None = Query(None, description="Carrier code, e.g. 6E"),
) -> dict:
    return dict(route=route, travel_date=travel_date, lead_days=lead_days, date_from=date_from, date_to=date_to, source=source, quality_status=quality_status, airline=airline)


@router.get("/fares", summary="Normalized fare observations (paginated, filterable)")
async def list_fares(filters: dict = Depends(_filters), pagination: Pagination = Depends(), db: AsyncDatabase = Depends(get_db)):
    return await _list_quotes(db, pagination, **filters)


@router.get("/quotes", summary="Alias of /fares")
async def list_quotes(filters: dict = Depends(_filters), pagination: Pagination = Depends(), db: AsyncDatabase = Depends(get_db)):
    return await _list_quotes(db, pagination, **filters)


@router.get("/quotes/{quote_id}", response_model=FlightQuoteRead, summary="One normalized quote")
async def get_quote(quote_id: str, db: AsyncDatabase = Depends(get_db)):
    try:
        quote = await FlightQuoteRepository(db).get(quote_id)
    except ValueError:
        quote = None
    if quote is None:
        raise NotFoundError("Quote not found")
    return quote


@router.get("/quotes/{quote_id}/provenance", summary="Quote -> raw observation -> collection run (full audit chain)")
async def get_quote_provenance(quote_id: str, db: AsyncDatabase = Depends(get_db)):
    try:
        quote = await FlightQuoteRepository(db).get(quote_id)
    except ValueError:
        quote = None
    if quote is None:
        raise NotFoundError("Quote not found")
    raw = await RawObservationRepository(db).get(quote.raw_observation_id) if quote.raw_observation_id else None
    try:
        run = await SearchRunRepository(db).get_by_id(quote.search_run_id)
    except ValueError:
        run = None
    if run and run.get("travel_date") is not None:
        run["travel_date"] = datetime_to_date(run["travel_date"])
    return {"quote": quote, "raw_observation": raw, "search_run": run}


@router.get("/fares/booking-window", response_model=list[BookingWindowFare], summary="Fare for a travel date by booking window (T+X)")
async def fares_by_booking_window(
    route: str = Query(..., description="Route code, e.g. DEL-BOM"),
    travel_date: date = Query(..., description="Date of travel"),
    db: AsyncDatabase = Depends(get_db),
):
    """For each window T+X: fares observed X days before ``travel_date`` for that travel date."""
    definition = _route_or_404(route)
    repo = FlightQuoteRepository(db)
    out = []
    for lead in LEAD_TIME_DAYS:
        quotes = await repo.search(_quote_query(definition, travel_date=travel_date, lead_days=lead), limit=200)
        out.append({"lead_days": lead, "window": window_name(lead), "observation_date": travel_date - timedelta(days=lead), **_fare_stats(quotes)})
    return out


@router.get("/fares/booking-window/compare", summary="Average fare by booking window over a date range")
async def booking_window_comparison(
    route: str | None = Query(None, description="Route code; omit for all monitored routes"),
    date_from: date | None = Query(None, description="Observation date from (default: 30 days before date_to)"),
    date_to: date | None = Query(None, description="Observation date to (default: latest available)"),
    db: AsyncDatabase = Depends(get_db),
):
    definition = _route_or_404(route) if route else None
    match: dict = {}
    if definition:
        match["route"] = definition.route_code
    if date_to is None:
        latest = await db["daily_cells"].find_one(match, sort=[("date", -1)])
        if latest is None:
            return {"route": route, "windows": [], "date_from": None, "date_to": None}
        date_to = datetime_to_date(latest["date"])
    date_from = date_from or date_to - timedelta(days=29)
    if (date_to - date_from).days > MAX_RANGE_DAYS:
        raise AppError(f"Date range may not exceed {MAX_RANGE_DAYS} days")
    match["date"] = {"$gte": date_to_datetime(date_from), "$lte": date_to_datetime(date_to)}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$lead_days", "mean_log": {"$avg": "$mean_log_fare"}, "n_obs": {"$sum": "$n_obs"}, "min_fare": {"$min": "$min_fare"}, "max_fare": {"$max": "$max_fare"}}},
        {"$sort": {"_id": 1}},
    ]
    rows = await (await db["daily_cells"].aggregate(pipeline)).to_list()
    reference = next((r for r in rows if r["_id"] == max(LEAD_TIME_DAYS)), None)
    windows = []
    for r in rows:
        gm = math.exp(r["mean_log"])
        windows.append(
            {
                "lead_days": r["_id"],
                "window": window_name(r["_id"]),
                "geometric_mean_fare": round(gm, 2),
                "min_fare": r["min_fare"],
                "max_fare": r["max_fare"],
                "observations": r["n_obs"],
                "premium_vs_longest_window_pct": round((gm / math.exp(reference["mean_log"]) - 1) * 100, 2) if reference else None,
            }
        )
    return {"route": definition.route_code if definition else "ALL", "date_from": date_from, "date_to": date_to, "windows": windows}


@router.get("/fares/daily", summary="Daily geometric-mean fare per booking window for a route")
async def daily_fares(
    route: str = Query(...),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncDatabase = Depends(get_db),
):
    definition = _route_or_404(route)
    match: dict = {"route": definition.route_code}
    if date_to is None:
        latest = await db["daily_cells"].find_one(match, sort=[("date", -1)])
        if latest is None:
            return {"route": definition.route_code, "series": []}
        date_to = datetime_to_date(latest["date"])
    date_from = date_from or date_to - timedelta(days=89)
    if (date_to - date_from).days > MAX_RANGE_DAYS:
        raise AppError(f"Date range may not exceed {MAX_RANGE_DAYS} days")
    match["date"] = {"$gte": date_to_datetime(date_from), "$lte": date_to_datetime(date_to)}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": {"d": "$date", "l": "$lead_days"}, "mean_log": {"$avg": "$mean_log_fare"}, "n": {"$sum": "$n_obs"}}},
        {"$sort": {"_id.d": 1, "_id.l": 1}},
    ]
    rows = await (await db["daily_cells"].aggregate(pipeline)).to_list()
    by_day: dict[str, dict] = {}
    for r in rows:
        day = datetime_to_date(r["_id"]["d"]).isoformat()
        by_day.setdefault(day, {"date": day})[window_name(r["_id"]["l"])] = round(math.exp(r["mean_log"]), 2)
    return {"route": definition.route_code, "date_from": date_from, "date_to": date_to, "windows": [window_name(l) for l in LEAD_TIME_DAYS], "series": list(by_day.values())}
