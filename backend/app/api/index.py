"""Airfare Price Index endpoints (read-only; series are precomputed by the index run).

Every response carries ``data_label`` (DEMO or REAL), the weighting
version/label, the base year and the calculation version, so a consumer
can never mistake a DEMO series for an official one.
"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_db
from app.core.errors import AppError, IndexNotAvailableError, NotFoundError
from app.core.lead_time import LEAD_TIME_DAYS
from app.core.routes import get_route
from app.db.bson_utils import date_to_datetime
from app.index_engine import service as index_service
from app.index_engine.calculators import CALCULATORS, DEFAULT_METHODOLOGY
from app.index_engine.engine import ELEMENTARY_METHOD
from app.index_engine.periods import Frequency
from app.repositories.flight_quote_repository import FlightQuoteRepository
from app.schemas.analytics import IndexSeriesOut

router = APIRouter(prefix="/index", tags=["index"])

MethodologyParam = Query(DEFAULT_METHODOLOGY, description=f"One of {sorted(CALCULATORS)}")


async def require_run(db: AsyncDatabase) -> dict:
    run = await index_service.current_run(db)
    if run is None:
        raise IndexNotAvailableError("No index has been computed yet. Run `python -m app.cli seed-demo` or the scheduled job.")
    return run


def _methodology(value: str) -> str:
    name = value.upper()
    if name not in CALCULATORS:
        raise AppError(f"Unknown methodology {value!r}", details={"allowed": sorted(CALCULATORS)})
    return name


def _filter_points(points: list[dict], start: date | None, end: date | None, limit: int | None) -> list[dict]:
    if start:
        points = [p for p in points if p["start"] >= start.isoformat()]
    if end:
        points = [p for p in points if p["start"] <= end.isoformat()]
    if limit:
        points = points[-limit:]
    return points


async def _series(db, run, series_id, start, end, limit) -> dict:
    doc = await index_service.get_series(db, run["_id"], series_id)
    if doc is None:
        raise NotFoundError(f"Series {series_id} not found in the current index run")
    doc["points"] = _filter_points(doc["points"], start, end, limit)
    return doc


_START = Query(None, description="First period start date (inclusive)")
_END = Query(None, description="Last period start date (inclusive)")
_LIMIT = Query(None, ge=1, le=5000, description="Return only the last N points")


@router.get("", response_model=IndexSeriesOut, summary="Overall index series (any methodology/frequency)")
async def get_index(
    methodology: str = MethodologyParam,
    frequency: Frequency = Frequency.MONTHLY,
    start: date | None = _START,
    end: date | None = _END,
    limit: int | None = _LIMIT,
    db: AsyncDatabase = Depends(get_db),
):
    run = await require_run(db)
    return await _series(db, run, f"{_methodology(methodology)}:{frequency.value}:overall:ALL", start, end, limit)


@router.get("/daily", response_model=IndexSeriesOut, summary="Daily overall index")
async def get_daily(methodology: str = MethodologyParam, start: date | None = _START, end: date | None = _END, limit: int | None = _LIMIT, db: AsyncDatabase = Depends(get_db)):
    run = await require_run(db)
    return await _series(db, run, f"{_methodology(methodology)}:daily:overall:ALL", start, end, limit)


@router.get("/weekly", response_model=IndexSeriesOut, summary="Weekly (ISO week) overall index")
async def get_weekly(methodology: str = MethodologyParam, start: date | None = _START, end: date | None = _END, limit: int | None = _LIMIT, db: AsyncDatabase = Depends(get_db)):
    run = await require_run(db)
    return await _series(db, run, f"{_methodology(methodology)}:weekly:overall:ALL", start, end, limit)


@router.get("/monthly", response_model=IndexSeriesOut, summary="Monthly overall index")
async def get_monthly(methodology: str = MethodologyParam, start: date | None = _START, end: date | None = _END, limit: int | None = _LIMIT, db: AsyncDatabase = Depends(get_db)):
    run = await require_run(db)
    return await _series(db, run, f"{_methodology(methodology)}:monthly:overall:ALL", start, end, limit)


@router.get("/route/{route}", response_model=IndexSeriesOut, summary="Route-level (elementary Jevons) index")
async def get_route_index(
    route: str,
    frequency: Frequency = Frequency.MONTHLY,
    lead_days: int | None = Query(None, description="Restrict to one booking window (T+N)"),
    start: date | None = _START,
    end: date | None = _END,
    limit: int | None = _LIMIT,
    db: AsyncDatabase = Depends(get_db),
):
    definition = get_route(route)
    if definition is None:
        raise NotFoundError(f"Route {route!r} is not a monitored route")
    run = await require_run(db)
    if lead_days is None:
        series_id = f"{ELEMENTARY_METHOD}:{frequency.value}:route:{definition.route_code}"
    else:
        if lead_days not in LEAD_TIME_DAYS:
            raise AppError(f"Unsupported booking window T+{lead_days}", details={"allowed": list(LEAD_TIME_DAYS)})
        series_id = f"{ELEMENTARY_METHOD}:{frequency.value}:route_window:{definition.route_code}|T+{lead_days}"
    return await _series(db, run, series_id, start, end, limit)


@router.get("/booking-window", response_model=IndexSeriesOut, summary="Index for one booking window across all routes")
async def get_booking_window_index(
    lead_days: int = Query(..., description="Booking window in days before travel (e.g. 15 for T+15)"),
    methodology: str = MethodologyParam,
    frequency: Frequency = Frequency.MONTHLY,
    start: date | None = _START,
    end: date | None = _END,
    limit: int | None = _LIMIT,
    db: AsyncDatabase = Depends(get_db),
):
    if lead_days not in LEAD_TIME_DAYS:
        raise AppError(f"Unsupported booking window T+{lead_days}", details={"allowed": list(LEAD_TIME_DAYS)})
    run = await require_run(db)
    return await _series(db, run, f"{_methodology(methodology)}:{frequency.value}:window:T+{lead_days}", start, end, limit)


@router.get("/methodologies", summary="All methodologies side by side for the overall index")
async def compare_methodologies(
    frequency: Frequency = Frequency.MONTHLY,
    start: date | None = _START,
    end: date | None = _END,
    limit: int | None = _LIMIT,
    db: AsyncDatabase = Depends(get_db),
):
    run = await require_run(db)
    out = {
        "run_id": run["_id"],
        "data_label": run["data_label"],
        "frequency": frequency.value,
        "default_methodology": DEFAULT_METHODOLOGY,
        "weighting": run["weighting"],
        "methodologies": [],
    }
    for name, calc in CALCULATORS.items():
        doc = await index_service.get_series(db, run["_id"], f"{name}:{frequency.value}:overall:ALL")
        if doc is None:
            continue
        out["methodologies"].append(
            {"methodology": name, "label": calc.label, "description": calc.description, "requires_weights": calc.requires_weights, "points": _filter_points(doc["points"], start, end, limit)}
        )
    return out


@router.get("/series", summary="Catalogue of every series in the current run (no points)")
async def list_series(db: AsyncDatabase = Depends(get_db)):
    run = await require_run(db)
    return {"run_id": run["_id"], "data_label": run["data_label"], "series": await index_service.list_series(db, run["_id"])}


@router.get("/runs/current", summary="Metadata of the current index run (reproducibility record)")
async def get_current_run(db: AsyncDatabase = Depends(get_db)):
    run = await require_run(db)
    run["run_id"] = run.pop("_id")
    return run


@router.get("/trace", summary="Trace an index value down to observations, sources and quality decisions")
async def trace(
    route: str = Query(..., description="Route code, e.g. DEL-BOM"),
    observation_date: date = Query(..., description="Observation day (IST) of the daily index point"),
    lead_days: int | None = Query(None),
    db: AsyncDatabase = Depends(get_db),
):
    definition = get_route(route)
    if definition is None:
        raise NotFoundError(f"Route {route!r} is not a monitored route")
    run = await require_run(db)
    code = definition.route_code
    series = await index_service.get_series(db, run["_id"], f"{ELEMENTARY_METHOD}:daily:route:{code}")
    point = next((p for p in (series or {}).get("points", []) if p["period"] == observation_date.isoformat()), None)

    cell_query: dict = {"route": code, "date": date_to_datetime(observation_date)}
    quote_query: dict = {"route.origin": definition.origin, "route.destination": definition.destination, "travel.observation_date": date_to_datetime(observation_date)}
    if lead_days is not None:
        cell_query["lead_days"] = lead_days
        quote_query["travel.lead_days"] = lead_days
    cells = await db[index_service.CELLS].find(cell_query, {"_id": 0}).sort([("lead_days", 1), ("airline", 1)]).to_list()
    quotes = await FlightQuoteRepository(db).search(quote_query, limit=500, sort=[("travel.lead_days", 1), ("flight.airline_code", 1)])
    return {
        "run_id": run["_id"],
        "data_label": run["data_label"],
        "route": code,
        "observation_date": observation_date.isoformat(),
        "index_point": point,
        "methodology": {"elementary": "Jevons (geometric mean of matched item relatives vs base year)", "calculation_version": run["calculation_version"]},
        "cells": cells,
        "observations": [
            {
                "quote_id": q.id,
                "search_run_id": q.search_run_id,
                "raw_observation_id": q.raw_observation_id,
                "source": q.source,
                "provenance": q.provenance,
                "airline_code": q.airline_code,
                "flight_number": q.flight_number,
                "lead_days": q.lead_days,
                "travel_date": q.travel_date,
                "search_datetime": q.search_datetime,
                "total_fare": q.total_fare,
                "currency": q.currency,
                "components_available": q.components_available,
                "availability_status": q.availability_status,
                "quality_status": q.quality_status,
                "quality_reason": q.quality_reason,
                "normalization_version": q.normalization_version,
                "extraction_version": q.extraction_version,
                "included_in_index": q.quality_status in ("VALIDATED", "PROVISIONAL") and q.provenance != "SYNTHETIC",
            }
            for q in quotes
        ],
    }
