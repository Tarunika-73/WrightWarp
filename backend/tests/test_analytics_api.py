"""Integration tests for the statistical API over a small, freshly seeded DEMO dataset.

A dedicated database (never the developer's) is seeded once per module
through the real backfill + index computation, then queried over HTTP.
"""
import asyncio
from datetime import date

import pytest
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient, MongoClient

from app.api.deps import get_db
from app.core.config import get_settings
from app.db.indexes import ensure_indexes
from app.db.mongodb import get_database
from app.demo.seed import seed_demo_history
from app.index_engine.service import run_index_computation
from app.main import app
from app.repositories.source_repository import SourceRepository

ANALYTICS_DB = "wrightwarp_test_analytics"
SEED_START = date(2024, 11, 1)
SEED_END = date(2025, 1, 20)


def _clear() -> None:
    client = MongoClient(get_settings().mongo_connection_uri)
    for name in client[ANALYTICS_DB].list_collection_names():
        client[ANALYTICS_DB].drop_collection(name)
    client.close()


@pytest.fixture(scope="module")
def api() -> TestClient:
    async def seed() -> None:
        client = AsyncMongoClient(get_settings().mongo_connection_uri, tz_aware=True)
        db = client[ANALYTICS_DB]
        await ensure_indexes(db)
        await SourceRepository(db).sync_registry()
        await seed_demo_history(db, start=SEED_START, end=SEED_END)
        await run_index_computation(db)
        await client.close()

    _clear()
    asyncio.run(seed())
    app.dependency_overrides[get_db] = lambda: get_database(ANALYTICS_DB)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        _clear()


def test_monthly_index_is_labelled_demo_and_anchored(api):
    body = api.get("/api/v1/index", params={"frequency": "monthly"}).json()
    assert body["data_label"] == "DEMO"
    assert body["weighting_label"] == "DEMO"
    assert body["base_year"] == 2024
    periods = [p["period"] for p in body["points"]]
    assert periods == ["2024-11", "2024-12", "2025-01"]
    assert all(p["value"] > 0 and p["n_obs"] > 0 for p in body["points"])


@pytest.mark.parametrize("path", ["/api/v1/index/daily", "/api/v1/index/weekly", "/api/v1/index/monthly"])
def test_frequency_shortcuts(path, api):
    response = api.get(path, params={"limit": 3, "methodology": "fisher"})
    assert response.status_code == 200
    body = response.json()
    assert body["methodology"] == "FISHER"
    assert len(body["points"]) == 3


def test_route_and_route_window_index(api):
    route = api.get("/api/v1/index/route/del-bom", params={"frequency": "weekly"}).json()
    assert route["scope"] == "route" and route["scope_key"] == "DEL-BOM"
    assert route["points"][0]["price"] > 0
    window = api.get("/api/v1/index/route/DEL-BOM", params={"lead_days": 1}).json()
    assert window["scope_key"] == "DEL-BOM|T+1"


def test_booking_window_index_and_methodology_comparison(api):
    assert api.get("/api/v1/index/booking-window", params={"lead_days": 45}).json()["scope_key"] == "T+45"
    comparison = api.get("/api/v1/index/methodologies").json()
    assert {m["methodology"] for m in comparison["methodologies"]} == {"LASPEYRES", "JEVONS", "PAASCHE", "FISHER"}


def test_index_validation_errors(api):
    bad_method = api.get("/api/v1/index", params={"methodology": "carli"})
    assert bad_method.status_code == 400
    assert bad_method.json()["error"]["code"] == "BAD_REQUEST"
    assert api.get("/api/v1/index/route/GOI-IXZ").status_code == 404
    assert api.get("/api/v1/index/booking-window", params={"lead_days": 10}).status_code == 400


def test_run_metadata_is_reproducibility_record(api):
    run = api.get("/api/v1/index/runs/current").json()
    for key in ("observation_count", "valid_observation_count", "excluded_observation_count", "source_count", "route_count", "weighting", "calculation_version", "created_at", "methodologies"):
        assert key in run
    assert run["valid_observation_count"] + run["excluded_observation_count"] == run["observation_count"]
    assert api.get("/api/v1/index/series").json()["series"]


def test_fares_pagination_and_filters(api):
    page = api.get("/api/v1/fares", params={"route": "DEL-BOM", "page_size": 5}).json()
    assert len(page["items"]) == 5
    assert page["page"]["total"] > 5
    sold_out = api.get("/api/v1/quotes", params={"quality_status": "SOLD_OUT", "page_size": 50}).json()
    assert all(q["quality_status"] == "SOLD_OUT" and q["total_fare"] is None for q in sold_out["items"])


def test_quote_provenance_chain(api):
    quote = api.get("/api/v1/fares", params={"page_size": 1}).json()["items"][0]
    assert api.get(f"/api/v1/quotes/{quote['id']}").status_code == 200
    chain = api.get(f"/api/v1/quotes/{quote['id']}/provenance").json()
    assert chain["raw_observation"]["_id"] == quote["raw_observation_id"]
    assert chain["raw_observation"]["payload_hash"] == quote["raw_quote_hash"]
    assert chain["search_run"]["_id"] == quote["search_run_id"]
    assert api.get("/api/v1/quotes/not-an-id").status_code == 404


def test_booking_window_answers_the_core_question(api):
    rows = api.get("/api/v1/fares/booking-window", params={"route": "DEL-BOM", "travel_date": "2025-01-20"}).json()
    assert [r["window"] for r in rows] == ["T+1", "T+7", "T+15", "T+30", "T+45"]
    assert rows[0]["observation_date"] == "2025-01-19"
    assert rows[-1]["observation_date"] == "2024-12-06"
    t1, t45 = rows[0]["geometric_mean_fare"], rows[-1]["geometric_mean_fare"]
    assert t1 and t45 and t1 > t45  # last-minute premium


def test_booking_window_comparison_and_daily_fares(api):
    cmp = api.get("/api/v1/fares/booking-window/compare", params={"route": "DEL-BOM"}).json()
    by = {w["window"]: w for w in cmp["windows"]}
    assert by["T+1"]["premium_vs_longest_window_pct"] > 0
    assert by["T+45"]["premium_vs_longest_window_pct"] == 0
    daily = api.get("/api/v1/fares/daily", params={"route": "BLR-HYD"}).json()
    assert daily["series"] and "T+1" in daily["series"][-1]


def test_quality_summary_accounts_for_every_observation(api):
    summary = api.get("/api/v1/quality/summary", params={"days": 30}).json()
    assert summary["total_observations"] == sum(s["count"] for s in summary["by_status"])
    assert summary["index_eligible"] + summary["excluded"] == summary["total_observations"]
    assert summary["timeline"]
    assert api.get("/api/v1/quality/rules").json()["rules"]


def test_backtest_is_clearly_demo(api):
    report = api.get("/api/v1/backtest").json()
    assert report["data_label"] == "DEMO"
    ref = report["references"][0]
    assert ref["reference_id"] == "DEMO_SIM_TRUTH"
    assert "NOT OFFICIAL" in ref["label"]
    assert ref["results"]["methodologies"]["LASPEYRES"]["daily"]["n_periods"] > 0


def test_overview_routes_meta_collections_trace(api):
    overview = api.get("/api/v1/stats/overview").json()
    assert overview["index_available"] is True
    assert overview["data_label"] == "DEMO"
    assert overview["current_index"]["value"] > 0
    assert len(overview["booking_windows"]) == 5
    routes = api.get("/api/v1/routes").json()
    assert len(routes) == 6 and all(r["weighting_label"] == "DEMO" for r in routes)
    assert "DEMO DATA" in api.get("/api/v1/meta").json()["data_notice"]
    runs = api.get("/api/v1/collections", params={"source": "DEMO_SIM", "page_size": 2}).json()
    assert len(runs["items"]) == 2
    trace = api.get("/api/v1/index/trace", params={"route": "DEL-BOM", "observation_date": "2025-01-10"}).json()
    assert trace["index_point"]["period"] == "2025-01-10"
    assert trace["observations"] and all("included_in_index" in o for o in trace["observations"])
