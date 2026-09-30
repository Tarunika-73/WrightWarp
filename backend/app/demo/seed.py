"""Historical DEMO backfill: simulated market -> full pipeline -> MongoDB.

Live collection only ever sees "today", but an index with base year 2024
needs history. This backfill generates the simulated market's
observations for every backfill day since ``SIM_START`` and pushes each
one through exactly the same ``process_observation`` (normalization +
quality engine) as live collection, leaving the same audit trail:
``search_runs`` -> ``raw_observations`` -> ``flight_quotes``. The only
difference is bulk inserts instead of one-at-a-time writes, and an
in-memory quality context instead of DB lookups.

Everything written is ``source=DEMO_SIM``, ``provenance=SIMULATED``.
``reset=True`` deletes previous ``DEMO_SIM`` documents only - never data
from any other source.
"""
import logging
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.collection.repository import compute_payload_hash
from app.core.enums import (
    INDEX_ELIGIBLE_QUALITY,
    DataProvenance,
    RawObservationStatus,
    SearchRunStatus,
)
from app.core.lead_time import LEAD_TIME_DAYS
from app.core.routes import list_route_codes
from app.db.bson_utils import date_to_datetime
from app.demo.market import SIM_SOURCE_ID, SIM_START, SIM_VERSION, backfill_dates, generate_observations
from app.index_engine.service import CELLS
from app.models.raw_observation import RawObservationDocument
from app.models.search_run import SearchRunDocument
from app.normalization.fares import IST
from app.normalization.pipeline import ObservationContext, process_observation
from app.quality.context import REFERENCE_WINDOW_DAYS, DedupTracker
from app.quality.engine import QualityContext, reference_from_log_fares
from app.repositories.flight_quote_repository import FlightQuoteRepository

logger = logging.getLogger("app.demo.seed")

BATCH_DAYS = 30


async def delete_demo_data(db: AsyncDatabase) -> dict:
    deleted = {}
    for name, query in (
        ("flight_quotes", {"source.id": SIM_SOURCE_ID}),
        ("raw_observations", {"source": SIM_SOURCE_ID}),
        ("search_runs", {"source": SIM_SOURCE_ID}),
        ("collection_errors", {"source": SIM_SOURCE_ID}),
    ):
        result = await db[name].delete_many(query)
        deleted[name] = result.deleted_count
    # Cells are derived data; they are rebuilt from whatever quotes remain.
    await db[CELLS].delete_many({})
    return deleted


class _TrailingReference:
    """In-memory equivalent of reading ``daily_cells`` for the trailing reference window."""

    def __init__(self) -> None:
        self._cells: dict[tuple[str, int], deque[tuple[date, float]]] = defaultdict(deque)

    def stats_before(self, route: str, lead: int, day: date):
        q = self._cells[(route, lead)]
        cutoff = day - timedelta(days=REFERENCE_WINDOW_DAYS)
        while q and q[0][0] < cutoff:
            q.popleft()
        return reference_from_log_fares([v for d, v in q if d < day])

    def add(self, route: str, lead: int, day: date, log_fares_by_airline: dict[str, list[float]]) -> None:
        for values in log_fares_by_airline.values():
            self._cells[(route, lead)].append((day, sum(values) / len(values)))


async def seed_demo_history(
    db: AsyncDatabase,
    *,
    start: date = SIM_START,
    end: date | None = None,
    reset: bool = True,
    progress: Callable[[str], None] | None = None,
) -> dict:
    import math

    say = progress or (lambda msg: logger.info(msg))
    end = end or (datetime.now(timezone.utc).astimezone(IST).date() - timedelta(days=1))
    if reset:
        say(f"deleted previous demo data: {await delete_demo_data(db)}")

    dates = backfill_dates(start, end)
    routes = list_route_codes()
    dedup = DedupTracker()
    reference = _TrailingReference()
    quotes_repo = FlightQuoteRepository(db)
    totals = defaultdict(int)

    for batch_start in range(0, len(dates), BATCH_DAYS):
        batch = dates[batch_start : batch_start + BATCH_DAYS]
        runs: list[dict] = []
        raws: list[dict] = []
        quotes = []
        for day in batch:
            for route in routes:
                origin, destination = route.split("-")
                for lead in LEAD_TIME_DAYS:
                    run_id = ObjectId()
                    payloads = generate_observations(route, day, lead)
                    started = datetime.combine(day, datetime.min.time(), tzinfo=IST).replace(hour=6).astimezone(timezone.utc)
                    ref = reference.stats_before(route, lead, day)
                    quality_context = QualityContext(
                        is_duplicate=dedup,
                        reference_for=lambda r, l, _ref=ref, _route=route, _lead=lead: _ref if (r, l) == (_route, _lead) else None,
                    )
                    request_parameters = {
                        "source_id": SIM_SOURCE_ID,
                        "origin": origin,
                        "destination": destination,
                        "travel_date": (day + timedelta(days=lead)).isoformat(),
                        "lead_days": lead,
                        "passenger_count": 1,
                        "cabin_class": "ECONOMY",
                    }
                    valid_logs: dict[str, list[float]] = defaultdict(list)
                    n_quotes = 0
                    for payload in payloads:
                        raw_id = ObjectId()
                        search_dt = datetime.fromisoformat(payload["observed_at"])
                        ctx = ObservationContext(
                            search_run_id=str(run_id),
                            source=SIM_SOURCE_ID,
                            origin=origin,
                            destination=destination,
                            travel_date=day + timedelta(days=lead),
                            lead_days=lead,
                            search_datetime=search_dt,
                            provenance=DataProvenance.SIMULATED,
                            raw_observation_id=str(raw_id),
                            raw_payload_hash=compute_payload_hash(payload),
                            extraction_version=SIM_VERSION,
                        )
                        processed = process_observation(payload, ctx, quality_context)
                        status = RawObservationStatus.NORMALIZED if processed.quote else RawObservationStatus.PARSE_FAILED
                        raw_doc = RawObservationDocument(
                            search_run_id=str(run_id),
                            source=SIM_SOURCE_ID,
                            collected_at=search_dt.astimezone(timezone.utc),
                            request_parameters=request_parameters,
                            raw_payload=payload,
                            payload_hash=ctx.raw_payload_hash,
                            status=status,
                            provenance=DataProvenance.SIMULATED,
                            quality_status=processed.assessment.status.value,
                            quality_reason=processed.assessment.reason,
                            extraction_version=SIM_VERSION,
                        ).model_dump(exclude={"id"})
                        raw_doc["_id"] = raw_id
                        raws.append(raw_doc)
                        totals[f"quality:{processed.assessment.status.value}"] += 1
                        if processed.quote is not None:
                            quotes.append(processed.quote)
                            n_quotes += 1
                            q = processed.quote
                            if q.quality_status in INDEX_ELIGIBLE_QUALITY and q.total_fare:
                                valid_logs[q.airline_code or "UNKNOWN"].append(math.log(q.total_fare))
                    reference.add(route, lead, day, valid_logs)

                    run_doc = SearchRunDocument(
                        source=SIM_SOURCE_ID,
                        origin=origin,
                        destination=destination,
                        route=route,
                        travel_date=date_to_datetime(day + timedelta(days=lead)),
                        lead_days=lead,
                        status=SearchRunStatus.SUCCESS if payloads else SearchRunStatus.NO_RESULTS,
                        started_at=started,
                        completed_at=started + timedelta(seconds=2),
                        records_found=len(payloads),
                        records_valid=n_quotes,
                    ).model_dump(exclude={"id"})
                    run_doc["_id"] = run_id
                    runs.append(run_doc)

        if runs:
            await db["search_runs"].insert_many(runs, ordered=False)
        if raws:
            await db["raw_observations"].insert_many(raws, ordered=False)
        await quotes_repo.insert_many(quotes)
        totals["search_runs"] += len(runs)
        totals["raw_observations"] += len(raws)
        totals["flight_quotes"] += len(quotes)
        say(f"seeded {batch[0]}..{batch[-1]}: runs={len(runs)} raw={len(raws)} quotes={len(quotes)}")

    return {"start": start.isoformat(), "end": end.isoformat(), "observation_days": len(dates), **totals}
