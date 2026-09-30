"""Builds a ``QualityContext`` from MongoDB for live collection.

The quality engine's hooks are synchronous and pure, so everything they
need is prefetched here in two queries per collection request:

* which of the request's dedup keys already exist in ``flight_quotes``
  (plus an in-batch "seen" set, so the second copy of a payload that
  appears twice in one response is also caught);
* the robust reference distribution for the route x booking window:
  daily elementary cells (``daily_cells``) from the trailing
  ``REFERENCE_WINDOW_DAYS`` days *before* the observation date - never
  including the day being judged, so a single bad day cannot vouch for
  itself.
"""
from datetime import date, timedelta

from pymongo.asynchronous.database import AsyncDatabase

from app.db.bson_utils import date_to_datetime
from app.quality.engine import QualityContext, ReferenceStats, reference_from_log_fares

REFERENCE_WINDOW_DAYS = 28

DAILY_CELLS_COLLECTION = "daily_cells"


class DedupTracker:
    """``is_duplicate`` hook: known keys from the DB plus keys seen earlier in this batch."""

    def __init__(self, existing: set[str] | None = None) -> None:
        self._seen: set[str] = set(existing or ())

    def __call__(self, key: str) -> bool:
        if key in self._seen:
            return True
        self._seen.add(key)
        return False


async def fetch_reference(db: AsyncDatabase, route: str, lead_days: int, before: date) -> ReferenceStats | None:
    start = date_to_datetime(before - timedelta(days=REFERENCE_WINDOW_DAYS))
    end = date_to_datetime(before)
    cursor = db[DAILY_CELLS_COLLECTION].find(
        {"route": route, "lead_days": lead_days, "date": {"$gte": start, "$lt": end}},
        {"mean_log_fare": 1, "_id": 0},
    )
    values = [doc["mean_log_fare"] async for doc in cursor]
    return reference_from_log_fares(values)


async def build_live_context(
    db: AsyncDatabase,
    *,
    route: str,
    lead_days: int,
    observation_date: date,
    dedup_keys: list[str],
) -> QualityContext:
    existing: set[str] = set()
    keys = [k for k in dedup_keys if k]
    if keys:
        cursor = db["flight_quotes"].find({"dedup_key": {"$in": keys}}, {"dedup_key": 1, "_id": 0})
        existing = {doc["dedup_key"] async for doc in cursor}
    reference = await fetch_reference(db, route, lead_days, observation_date)

    def reference_for(r: str, lead: int) -> ReferenceStats | None:
        return reference if (r == route and lead == lead_days) else None

    return QualityContext(is_duplicate=DedupTracker(existing), reference_for=reference_for)
