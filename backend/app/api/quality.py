"""Data-quality monitoring endpoints."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_db
from app.core.enums import INDEX_ELIGIBLE_QUALITY
from app.db.bson_utils import date_to_datetime, datetime_to_date
from app.quality.engine import (
    MAX_PLAUSIBLE_FARE_INR,
    MIN_PLAUSIBLE_FARE_INR,
    MIN_REFERENCE_SAMPLE,
    OUTLIER_Z_THRESHOLD,
    QUALITY_RULES_VERSION,
)
from app.quality.context import REFERENCE_WINDOW_DAYS

router = APIRouter(prefix="/quality", tags=["quality"])


@router.get("/summary", summary="Quality decisions: counts by status, top reasons, per source, per day")
async def quality_summary(
    days: int = Query(90, ge=1, le=1100, description="Timeline length in days, ending at the latest observation"),
    db: AsyncDatabase = Depends(get_db),
):
    quotes = db["flight_quotes"]
    latest = await quotes.find_one({"travel.observation_date": {"$ne": None}}, sort=[("travel.observation_date", -1)], projection={"travel.observation_date": 1})
    by_status = await (await quotes.aggregate([{"$group": {"_id": "$quality.status", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}])).to_list()
    by_source = await (
        await quotes.aggregate([{"$group": {"_id": {"s": "$source.id", "q": "$quality.status"}, "n": {"$sum": 1}}}])
    ).to_list()
    reasons = await (
        await quotes.aggregate(
            [
                {"$match": {"quality.status": {"$nin": sorted(INDEX_ELIGIBLE_QUALITY)}}},
                {"$group": {"_id": {"s": "$quality.status", "r": "$quality.reason"}, "n": {"$sum": 1}}},
                {"$sort": {"n": -1}},
                {"$limit": 200},
            ]
        )
    ).to_list()
    # Collapse numeric detail (e.g. "robust_z=5.21") into a rule name for the top-reasons table.
    reason_counts: dict[tuple[str, str], int] = {}
    for r in reasons:
        rule = (r["_id"]["r"] or "").split(";")[0].split(":")[0].split("=")[0]
        key = (r["_id"]["s"], rule)
        reason_counts[key] = reason_counts.get(key, 0) + r["n"]
    top_reasons = [{"status": s, "rule": rule, "count": n} for (s, rule), n in sorted(reason_counts.items(), key=lambda kv: -kv[1])[:15]]

    timeline = []
    if latest:
        end = datetime_to_date(latest["travel"]["observation_date"])
        start = end - timedelta(days=days - 1)
        rows = await (
            await quotes.aggregate(
                [
                    {"$match": {"travel.observation_date": {"$gte": date_to_datetime(start), "$lte": date_to_datetime(end)}}},
                    {"$group": {"_id": {"d": "$travel.observation_date", "q": "$quality.status"}, "n": {"$sum": 1}}},
                    {"$sort": {"_id.d": 1}},
                ]
            )
        ).to_list()
        by_day: dict[str, dict] = {}
        for r in rows:
            day = datetime_to_date(r["_id"]["d"]).isoformat()
            by_day.setdefault(day, {"date": day})[r["_id"]["q"]] = r["n"]
        timeline = list(by_day.values())

    total = sum(r["n"] for r in by_status)
    eligible = sum(r["n"] for r in by_status if r["_id"] in INDEX_ELIGIBLE_QUALITY)
    sources: dict[str, dict] = {}
    for r in by_source:
        sources.setdefault(r["_id"]["s"], {"source": r["_id"]["s"]})[r["_id"]["q"]] = r["n"]
    return {
        "total_observations": total,
        "index_eligible": eligible,
        "excluded": total - eligible,
        "eligible_statuses": sorted(INDEX_ELIGIBLE_QUALITY),
        "by_status": [{"status": r["_id"], "count": r["n"]} for r in by_status],
        "by_source": list(sources.values()),
        "top_reasons": top_reasons,
        "timeline": timeline,
    }


@router.get("/rules", summary="The quality rules and thresholds in force")
async def quality_rules():
    return {
        "version": QUALITY_RULES_VERSION,
        "severity_order": ["REJECTED", "MISSING", "SOLD_OUT", "DUPLICATE", "REVIEW_REQUIRED", "OUTLIER", "PROVISIONAL", "VALIDATED"],
        "index_eligible": sorted(INDEX_ELIGIBLE_QUALITY),
        "rules": [
            {"rule": "required_fields", "outcome": "REJECTED", "detail": "source, origin, destination, travel_date, search_datetime, lead_days must be present"},
            {"rule": "route", "outcome": "REJECTED / REVIEW_REQUIRED", "detail": "3-letter uppercase IATA codes, origin != destination; routes outside the master list need review"},
            {"rule": "search_timestamp", "outcome": "REJECTED", "detail": "timezone-aware, not in the future"},
            {"rule": "travel_date", "outcome": "REJECTED", "detail": "not before the observation date, at most 365 days ahead"},
            {"rule": "lead_time", "outcome": "REJECTED / REVIEW_REQUIRED", "detail": "configured booking window; declared vs actual lead time within 1 day"},
            {"rule": "availability", "outcome": "SOLD_OUT / MISSING / REJECTED", "detail": "sold-out and cancelled flights kept as SOLD_OUT, never priced"},
            {"rule": "currency", "outcome": "REJECTED / REVIEW_REQUIRED", "detail": "INR only; no FX conversion is invented"},
            {"rule": "fare_value", "outcome": "MISSING / REJECTED", "detail": f"total fare present, positive, within INR {MIN_PLAUSIBLE_FARE_INR:.0f}..{MAX_PLAUSIBLE_FARE_INR:.0f}"},
            {"rule": "fare_components", "outcome": "REJECTED / REVIEW_REQUIRED", "detail": "no negative components; mandatory components must sum to total within max(INR 1, 1%)"},
            {"rule": "duplicate", "outcome": "DUPLICATE", "detail": "same source, flight, travel date, cabin and observation day seen before"},
            {"rule": "outlier", "outcome": "OUTLIER", "detail": f"|modified z| > {OUTLIER_Z_THRESHOLD} vs median/MAD of the route x window's trailing {REFERENCE_WINDOW_DAYS}-day cells (needs >= {MIN_REFERENCE_SAMPLE} cells)"},
        ],
    }
