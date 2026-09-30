"""One scheduled collection pass: every monitored route x booking window x cleared source.

Triggered by Vercel Cron (``GET /api/v1/cron/daily``) or ``python -m app.cli
collect-today``. Only sources that are ``IMPLEMENTED`` and ``enabled`` are
used - today that means the DEMO_SIM simulator in demo mode, since no real
airline/OTA has cleared compliance review. After collecting, the recent
daily cells are rebuilt and every index series is recomputed.

Designed to fit in one serverless invocation: the demo source makes no
network calls, so a full pass is ~30 requests of local work plus MongoDB
writes. A real browser-based source would NOT run here - see
docs/ARCHITECTURE.md ("Worker architecture").
"""
import logging
import time
from datetime import datetime, timedelta, timezone

from pymongo.asynchronous.database import AsyncDatabase

from app.collection.adapters.registry import adapter_registry
from app.collection.service import CollectionService
from app.core.config import get_settings
from app.core.enums import CollectionOutcome, SourceStatus
from app.core.lead_time import LEAD_TIME_DAYS
from app.core.routes import list_routes
from app.core.sources import list_sources
from app.index_engine.service import run_index_computation
from app.normalization.fares import observation_date
from app.schemas.collection import CollectionRequest

logger = logging.getLogger("app.scheduling")

JOBS = "scheduled_jobs"


def collectable_source_ids() -> list[str]:
    settings = get_settings()
    ids = []
    for source in list_sources():
        if source.status != SourceStatus.IMPLEMENTED or not source.enabled:
            continue
        if source.source_id == "MOCK":
            continue  # test fixture only
        if source.source_id == "DEMO_SIM" and not settings.demo_mode:
            continue
        if adapter_registry.is_registered(source.source_id):
            ids.append(source.source_id)
    return ids


def build_requests(source_ids: list[str], *, today=None) -> list[CollectionRequest]:
    today = today or observation_date(datetime.now(timezone.utc))
    return [
        CollectionRequest(
            source_id=source_id,
            origin=route.origin,
            destination=route.destination,
            travel_date=today + timedelta(days=lead),
            lead_days=lead,
        )
        for source_id in source_ids
        for route in list_routes()
        for lead in LEAD_TIME_DAYS
    ]


async def run_daily_collection(db: AsyncDatabase, *, recompute_index: bool = True) -> dict:
    started = time.monotonic()
    started_at = datetime.now(timezone.utc)
    source_ids = collectable_source_ids()
    requests = build_requests(source_ids)
    service = CollectionService(db, backoff_seconds=0.5)
    results = await service.run_batch(requests)

    outcomes: dict[str, int] = {}
    for r in results:
        outcomes[r.outcome] = outcomes.get(r.outcome, 0) + 1
    summary = {
        "job": "daily_collection",
        "started_at": started_at,
        "sources": source_ids,
        "requests": len(requests),
        "outcomes": outcomes,
        "quotes_normalized": sum(r.quotes_normalized for r in results),
        "failed": sum(1 for r in results if r.outcome == CollectionOutcome.FAILED.value),
    }
    if recompute_index and summary["quotes_normalized"]:
        try:
            run = await run_index_computation(db, since=observation_date(started_at) - timedelta(days=2))
            summary["index_run_id"] = run["_id"]
        except Exception as exc:  # noqa: BLE001 - recorded, not raised: collection already succeeded
            logger.exception("daily_index_recompute_failed")
            summary["index_error"] = type(exc).__name__
    summary["duration_seconds"] = round(time.monotonic() - started, 3)
    summary["completed_at"] = datetime.now(timezone.utc)
    await db[JOBS].insert_one(dict(summary))
    logger.info("daily_collection_completed requests=%s outcomes=%s duration_s=%s", len(requests), outcomes, summary["duration_seconds"])
    return summary
