"""Dashboard overview and application metadata."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.enums import SourceStatus
from app.core.lead_time import LEAD_TIME_WINDOWS
from app.core.routes import list_route_codes
from app.core.sources import list_sources
from app.index_engine import service as index_service
from app.index_engine.calculators import CALCULATORS, DEFAULT_METHODOLOGY
from app.index_engine.engine import ELEMENTARY_METHOD
from app.index_engine.weights import active_weight_set

router = APIRouter(tags=["overview"])


def _change(points: list[dict], back: int) -> float | None:
    if len(points) <= back:
        return None
    old, new = points[-1 - back]["value"], points[-1]["value"]
    return round((new / old - 1) * 100, 3) if old else None


def _value_on_or_before(points: list[dict], day: date) -> dict | None:
    candidates = [p for p in points if p["start"] <= day.isoformat()]
    return candidates[-1] if candidates else None


def _active_sources() -> list[dict]:
    settings = get_settings()
    out = []
    for s in list_sources():
        if s.status != SourceStatus.IMPLEMENTED or not s.enabled or s.source_id == "MOCK":
            continue
        if s.source_id == "DEMO_SIM" and not settings.demo_mode:
            continue
        out.append({"source_id": s.source_id, "display_name": s.display_name, "data_provenance": s.data_provenance.value})
    return out


@router.get("/meta", summary="What this deployment is: data mode, labels, windows, routes, methodologies")
async def meta():
    settings = get_settings()
    weights = active_weight_set(settings.index_base_year)
    return {
        "app": settings.app_name,
        "environment": settings.environment,
        "demo_mode": settings.demo_mode,
        "data_notice": (
            "DEMO DATA: every fare and index shown is SIMULATED by the WrightWarp market model. "
            "No real airline/OTA source is currently cleared for collection, and route weights are DEMO values, not DGCA data."
            if settings.demo_mode
            else "Figures derive from compliance-cleared sources; see /api/v1/sources."
        ),
        "base_year": settings.index_base_year,
        "base_value": 100,
        "booking_windows": [{"name": w.name, "days": w.days} for w in LEAD_TIME_WINDOWS],
        "routes": list(list_route_codes()),
        "methodologies": [{"name": c.name, "label": c.label, "description": c.description, "requires_weights": c.requires_weights} for c in CALCULATORS.values()],
        "default_methodology": DEFAULT_METHODOLOGY,
        "weighting": weights.metadata() | {"description": weights.description},
    }


@router.get("/stats/overview", summary="Everything the dashboard's overview page needs, in one call")
async def overview(db: AsyncDatabase = Depends(get_db)):
    run = await index_service.current_run(db)
    active_sources = _active_sources()
    last_run = await db["search_runs"].find_one({"source": {"$ne": "MOCK"}, "completed_at": {"$ne": None}}, sort=[("completed_at", -1)], projection={"completed_at": 1, "source": 1})
    last_job = await db["scheduled_jobs"].find_one({}, sort=[("started_at", -1)], projection={"_id": 0})
    base = {
        "active_sources": active_sources,
        "last_collection_at": last_run["completed_at"] if last_run else None,
        "last_scheduled_job": last_job,
    }
    if run is None:
        return {"index_available": False, **base}

    rid = run["_id"]
    wanted = [f"{DEFAULT_METHODOLOGY}:{f}:overall:ALL" for f in ("daily", "weekly", "monthly")]
    wanted += [f"{ELEMENTARY_METHOD}:daily:route:{r}" for r in list_route_codes()]
    wanted += [f"{DEFAULT_METHODOLOGY}:monthly:window:{w.name}" for w in LEAD_TIME_WINDOWS]
    fetched = await index_service.get_series_many(db, rid, wanted)

    async def points(series_id: str) -> list[dict]:
        doc = fetched.get(series_id)
        return doc["points"] if doc else []

    daily = await points(f"{DEFAULT_METHODOLOGY}:daily:overall:ALL")
    weekly = await points(f"{DEFAULT_METHODOLOGY}:weekly:overall:ALL")
    monthly = await points(f"{DEFAULT_METHODOLOGY}:monthly:overall:ALL")
    latest = daily[-1] if daily else None

    movers = []
    for route in list_route_codes():
        rp = await points(f"{ELEMENTARY_METHOD}:daily:route:{route}")
        if not rp:
            continue
        last = rp[-1]
        ref = _value_on_or_before(rp, date.fromisoformat(last["start"]) - timedelta(days=30))
        movers.append(
            {
                "route": route,
                "latest_period": last["period"],
                "latest_value": last["value"],
                "latest_price": last.get("price"),
                "change_30d_pct": round((last["value"] / ref["value"] - 1) * 100, 2) if ref else None,
            }
        )
    ranked = sorted((m for m in movers if m["change_30d_pct"] is not None), key=lambda m: m["change_30d_pct"], reverse=True)

    windows = []
    for w in LEAD_TIME_WINDOWS:
        wp = await points(f"{DEFAULT_METHODOLOGY}:monthly:window:{w.name}")
        windows.append({"window": w.name, "days": w.days, "latest_value": wp[-1]["value"] if wp else None, "latest_period": wp[-1]["period"] if wp else None})

    yoy = None
    if monthly:
        last_month = monthly[-1]["period"]
        prior = f"{int(last_month[:4]) - 1}{last_month[4:]}"
        prev = next((p for p in monthly if p["period"] == prior), None)
        if prev:
            yoy = round((monthly[-1]["value"] / prev["value"] - 1) * 100, 2)

    return {
        "index_available": True,
        **base,
        "run_id": rid,
        "data_label": run["data_label"],
        "calculated_at": run["created_at"],
        "methodology": DEFAULT_METHODOLOGY,
        "base_year": run["base_year"],
        "weighting": run["weighting"],
        "current_index": latest,
        "change_1d_pct": _change(daily, 1),
        "change_7d_pct": _change(daily, 7),
        "change_mom_pct": _change(monthly, 1),
        "change_yoy_pct": yoy,
        "daily_trend": daily[-90:],
        "weekly_trend": weekly[-52:],
        "monthly_trend": monthly,
        "top_increases": ranked[:3],
        "top_decreases": list(reversed(ranked[-3:])) if ranked else [],
        "routes": movers,
        "booking_windows": windows,
        "quality": {
            "observation_count": run.get("observation_count"),
            "valid_observation_count": run.get("valid_observation_count"),
            "excluded_observation_count": run.get("excluded_observation_count"),
            "by_quality_status": run.get("by_quality_status"),
        },
        "observation_period": {"first": run.get("first_observation_date"), "last": run.get("last_observation_date")},
    }
