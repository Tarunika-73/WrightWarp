"""MongoDB side of the index engine: build cells, compute, store, read.

Collections:

* ``daily_cells``   - elementary cells (observation day x route x window x
  carrier), rebuilt from ``flight_quotes`` by ``rebuild_cells``. Also the
  outlier reference the quality engine reads (``app.quality.context``).
* ``index_runs``    - one document per computation: inputs, counts,
  methodology list, weighting version, timings. The reproducibility record.
* ``index_series``  - one document per series (methodology x frequency x
  scope), tagged with the ``run_id`` that produced it.
* ``index_meta``    - single document ``{_id: "current"}`` naming the run
  readers should use. It is switched only after a run's series are fully
  written, so readers never see a half-written run.
* ``backtest_runs`` - backtest reports, tagged with the index ``run_id``.

Which observations feed the index: quality status in
``INDEX_ELIGIBLE_QUALITY`` and provenance REAL or SIMULATED. SYNTHETIC
observations (the MOCK test fixture) never do.
"""
import logging
import time
import uuid
from datetime import date, datetime, timedelta, timezone

from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings
from app.core.enums import INDEX_ELIGIBLE_QUALITY, DataLabel, DataProvenance
from app.core.lead_time import LEAD_TIME_DAYS
from app.core.routes import list_route_codes
from app.db.bson_utils import date_to_datetime, datetime_to_date
from app.index_engine.backtest import BACKTEST_VERSION, SimulatorTruth, compare_series, run_simulator_backtest
from app.index_engine.calculators import DEFAULT_METHODOLOGY, IndexCalculationError
from app.index_engine.engine import CALCULATION_VERSION, Cell, compute_series
from app.index_engine.periods import Frequency
from app.index_engine.weights import active_weight_set

logger = logging.getLogger("app.index_engine")

CELLS = "daily_cells"
RUNS = "index_runs"
SERIES = "index_series"
META = "index_meta"
BACKTESTS = "backtest_runs"
REFERENCE_SERIES = "reference_series"

INDEX_PROVENANCES = [DataProvenance.REAL.value, DataProvenance.SIMULATED.value]


def eligible_quote_filter(since: date | None = None) -> dict:
    query: dict = {
        "quality.status": {"$in": sorted(INDEX_ELIGIBLE_QUALITY)},
        "provenance.data_type": {"$in": INDEX_PROVENANCES},
        "fare.total_fare": {"$gt": 0},
        "travel.observation_date": {"$ne": None},
    }
    if since is not None:
        query["travel.observation_date"] = {"$gte": date_to_datetime(since)}
    return query


async def ensure_indexes(db: AsyncDatabase) -> None:
    await db[CELLS].create_index([("date", 1), ("route", 1), ("lead_days", 1), ("airline", 1)], unique=True)
    await db[CELLS].create_index([("route", 1), ("lead_days", 1), ("date", -1)])
    await db[SERIES].create_index([("run_id", 1), ("series_id", 1)], unique=True)
    await db[RUNS].create_index([("created_at", -1)])
    await db[BACKTESTS].create_index([("created_at", -1)])


async def rebuild_cells(db: AsyncDatabase, *, since: date | None = None) -> int:
    """(Re)aggregate eligible quotes into daily cells from ``since`` (or everything)."""
    pipeline = [
        {"$match": eligible_quote_filter(since)},
        {
            "$group": {
                "_id": {
                    "d": "$travel.observation_date",
                    "o": "$route.origin",
                    "de": "$route.destination",
                    "l": "$travel.lead_days",
                    "a": {"$ifNull": ["$flight.airline_code", "UNKNOWN"]},
                },
                "n": {"$sum": 1},
                "sum_log": {"$sum": {"$ln": "$fare.total_fare"}},
                "min_fare": {"$min": "$fare.total_fare"},
                "max_fare": {"$max": "$fare.total_fare"},
                "provenance": {"$addToSet": "$provenance.data_type"},
                "sources": {"$addToSet": "$source.id"},
            }
        },
    ]
    cursor = await db["flight_quotes"].aggregate(pipeline, allowDiskUse=True)
    docs = []
    async for g in cursor:
        key = g["_id"]
        docs.append(
            {
                "date": key["d"],
                "route": f"{key['o']}-{key['de']}",
                "lead_days": key["l"],
                "airline": key["a"],
                "n_obs": g["n"],
                "mean_log_fare": g["sum_log"] / g["n"],
                "min_fare": g["min_fare"],
                "max_fare": g["max_fare"],
                "provenance": sorted(g["provenance"]),
                "sources": sorted(g["sources"]),
            }
        )
    # Replace the affected date range wholesale, so a cell whose quotes were
    # all re-flagged (e.g. as outliers) disappears instead of lingering.
    await db[CELLS].delete_many({} if since is None else {"date": {"$gte": date_to_datetime(since)}})
    for i in range(0, len(docs), 5000):
        await db[CELLS].insert_many(docs[i : i + 5000], ordered=False)
    return len(docs)


async def load_cells(db: AsyncDatabase) -> tuple[list[Cell], set[str]]:
    cells: list[Cell] = []
    provenance: set[str] = set()
    cursor = db[CELLS].find({}, {"_id": 0, "date": 1, "route": 1, "lead_days": 1, "airline": 1, "mean_log_fare": 1, "n_obs": 1, "provenance": 1})
    async for doc in cursor:
        cells.append(
            Cell(
                date=datetime_to_date(doc["date"]),
                route=doc["route"],
                lead_days=doc["lead_days"],
                airline=doc["airline"],
                mean_log_fare=doc["mean_log_fare"],
                n_obs=doc["n_obs"],
            )
        )
        provenance.update(doc.get("provenance", []))
    return cells, provenance


def data_label_for(provenance: set[str]) -> str:
    if provenance & {DataProvenance.SIMULATED.value, DataProvenance.SYNTHETIC.value}:
        return DataLabel.DEMO.value
    return DataLabel.REAL.value


async def _quote_statistics(db: AsyncDatabase) -> dict:
    by_status = await (await db["flight_quotes"].aggregate([{"$group": {"_id": "$quality.status", "n": {"$sum": 1}}}])).to_list()
    by_source = await (await db["flight_quotes"].aggregate([{"$group": {"_id": "$source.id", "n": {"$sum": 1}}}])).to_list()
    status_counts = {d["_id"]: d["n"] for d in by_status}
    total = sum(status_counts.values())
    valid = sum(n for s, n in status_counts.items() if s in INDEX_ELIGIBLE_QUALITY)
    return {
        "observation_count": total,
        "valid_observation_count": valid,
        "excluded_observation_count": total - valid,
        "by_quality_status": status_counts,
        "by_source": {d["_id"]: d["n"] for d in by_source},
        "source_count": len(by_source),
    }


async def run_index_computation(db: AsyncDatabase, *, rebuild: bool = True, since: date | None = None) -> dict:
    """Rebuild cells, compute every series, run the backtest, then switch the current run."""
    settings = get_settings()
    started = time.monotonic()
    run_id = uuid.uuid4().hex
    if rebuild:
        await rebuild_cells(db, since=since)
    cells, provenance = await load_cells(db)
    weight_set = active_weight_set(settings.index_base_year)
    series = compute_series(cells, base_year=settings.index_base_year, weight_set=weight_set)
    label = data_label_for(provenance)
    now = datetime.now(timezone.utc)
    quote_stats = await _quote_statistics(db)
    dates = sorted({c.date for c in cells})

    series_docs = [
        {
            "run_id": run_id,
            "series_id": s.series_id,
            "methodology": s.methodology,
            "frequency": s.frequency.value,
            "scope": s.scope,
            "scope_key": s.scope_key,
            "base_year": settings.index_base_year,
            "base_value": 100.0,
            "data_label": label,
            "weighting_version": weight_set.version,
            "weighting_label": weight_set.label,
            "calculation_version": CALCULATION_VERSION,
            "calculated_at": now,
            "points": s.points,
        }
        for s in series
    ]
    for i in range(0, len(series_docs), 50):
        await db[SERIES].insert_many(series_docs[i : i + 50], ordered=False)

    run_doc = {
        "_id": run_id,
        "created_at": now,
        "calculation_version": CALCULATION_VERSION,
        "data_label": label,
        "provenance_in_inputs": sorted(provenance),
        "base_year": settings.index_base_year,
        "base_value": 100.0,
        "default_methodology": DEFAULT_METHODOLOGY,
        "methodologies": sorted({s.methodology for s in series}),
        "frequencies": [f.value for f in Frequency],
        "weighting": weight_set.metadata(),
        "booking_windows": list(LEAD_TIME_DAYS),
        "cell_count": len(cells),
        "route_count": len({c.route for c in cells}),
        "first_observation_date": dates[0].isoformat() if dates else None,
        "last_observation_date": dates[-1].isoformat() if dates else None,
        "series_count": len(series_docs),
        **quote_stats,
        "duration_seconds": None,
    }

    backtest = None
    try:
        backtest = await _run_backtest(db, run_id=run_id, series=series, dates=dates, weight_set=weight_set, label=label)
    except Exception:  # noqa: BLE001 - a failing backtest must not block publishing the index
        logger.exception("backtest_failed run_id=%s", run_id)

    run_doc["backtest_id"] = backtest["_id"] if backtest else None
    run_doc["duration_seconds"] = round(time.monotonic() - started, 3)
    await db[RUNS].insert_one(run_doc)

    previous = await db[META].find_one({"_id": "current"})
    await db[META].replace_one({"_id": "current"}, {"_id": "current", "run_id": run_id, "updated_at": now}, upsert=True)
    if previous and previous.get("run_id") != run_id:
        await db[SERIES].delete_many({"run_id": {"$ne": run_id}})
        # Keep run documents and backtests (small) as the audit history.
    logger.info(
        "index_run_completed run_id=%s series=%s cells=%s duration_s=%s label=%s",
        run_id,
        len(series_docs),
        len(cells),
        run_doc["duration_seconds"],
        label,
    )
    return run_doc


async def _run_backtest(db: AsyncDatabase, *, run_id: str, series, dates, weight_set, label: str) -> dict | None:
    settings = get_settings()
    routes = list(list_route_codes())
    report: dict = {
        "_id": uuid.uuid4().hex,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc),
        "backtest_version": BACKTEST_VERSION,
        "data_label": label,
        "default_methodology": DEFAULT_METHODOLOGY,
        "base_year": settings.index_base_year,
        "excluded_base_year_from_metrics": True,
        "references": [],
    }
    if label == DataLabel.DEMO.value and settings.demo_mode:
        truth = SimulatorTruth(base_year=settings.index_base_year, weight_set=weight_set, observation_dates=dates, windows=list(LEAD_TIME_DAYS))
        report["references"].append(
            {
                "reference_id": SimulatorTruth.reference_id,
                "label": SimulatorTruth.label,
                "data_label": DataLabel.DEMO.value,
                "description": (
                    "Latent price process of the demo market simulator. Measures how accurately the "
                    "pipeline recovers a known index from noisy, gappy, partly corrupted observations. "
                    "This is NOT a comparison with official statistics."
                ),
                "results": run_simulator_backtest(series, truth, routes=routes, default_method=DEFAULT_METHODOLOGY),
            }
        )

    # Any stored official/external reference series (none ships with the repo).
    async for ref in db[REFERENCE_SERIES].find({}):
        freq = ref.get("frequency", "monthly")
        estimated = next(
            (s for s in series if s.scope == "overall" and s.methodology == DEFAULT_METHODOLOGY and s.frequency.value == freq),
            None,
        )
        if estimated is None:
            continue
        metrics = compare_series({p["period"]: p["value"] for p in estimated.points}, {p["period"]: p["value"] for p in ref.get("points", [])})
        report["references"].append(
            {
                "reference_id": str(ref.get("reference_id", ref["_id"])),
                "label": ref.get("label", "REFERENCE"),
                "data_label": DataLabel.REFERENCE.value,
                "description": ref.get("description", ""),
                "results": {"overall": {freq: metrics.as_dict() if metrics else None}},
            }
        )
    if not report["references"]:
        report["note"] = "No reference series available: nothing to backtest against."
    await db[BACKTESTS].insert_one(report)
    return report


# ------------------------------------------------------------------ reads


async def current_run(db: AsyncDatabase) -> dict | None:
    meta = await db[META].find_one({"_id": "current"})
    if not meta:
        return None
    return await db[RUNS].find_one({"_id": meta["run_id"]})


async def get_series(db: AsyncDatabase, run_id: str, series_id: str) -> dict | None:
    return await db[SERIES].find_one({"run_id": run_id, "series_id": series_id}, {"_id": 0})


async def get_series_many(db: AsyncDatabase, run_id: str, series_ids: list[str]) -> dict[str, dict]:
    docs = await db[SERIES].find({"run_id": run_id, "series_id": {"$in": series_ids}}, {"_id": 0}).to_list()
    return {d["series_id"]: d for d in docs}


async def list_series(db: AsyncDatabase, run_id: str, query: dict | None = None, *, with_points: bool = False) -> list[dict]:
    projection = {"_id": 0} if with_points else {"_id": 0, "points": 0}
    return await db[SERIES].find({"run_id": run_id, **(query or {})}, projection).to_list()


async def latest_backtest(db: AsyncDatabase) -> dict | None:
    return await db[BACKTESTS].find_one({}, sort=[("created_at", -1)])


def recent_since(days: int) -> date:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date()


__all__ = [
    "IndexCalculationError",
    "run_index_computation",
    "rebuild_cells",
    "current_run",
    "get_series",
    "list_series",
    "latest_backtest",
]
