from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.enums import QualityStatus
from app.main import app
from app.repositories.flight_quote_repository import FlightQuoteRepository
from app.scheduling.daily import build_requests, collectable_source_ids, run_daily_collection


def test_unknown_path_has_consistent_error_shape(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["request_id"]
    assert body["detail"] == body["error"]["message"]


def test_validation_error_shape(client):
    response = client.post("/api/v1/collections", json={"source_id": "MOCK", "origin": "DEL"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(body["error"]["details"], list)


def test_unexpected_errors_never_leak_details(monkeypatch):
    import app.api.stats as stats

    def boom(*_args, **_kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(stats, "active_weight_set", boom)
    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.get("/api/v1/meta")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in response.text
    assert "Traceback" not in response.text


def test_cron_endpoints_refuse_without_configured_secret(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "cron_secret", None)
    response = client.get("/api/v1/cron/daily", headers={"Authorization": "Bearer anything"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "NOT_CONFIGURED"


def test_cron_endpoints_reject_wrong_token(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "cron_secret", "correct-horse")
    assert client.get("/api/v1/cron/daily").status_code == 401
    assert client.get("/api/v1/cron/daily", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/api/v1/admin/recompute-index", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/api/v1/backtest/run").status_code == 401


def test_only_cleared_non_fixture_sources_are_scheduled():
    assert collectable_source_ids() == ["DEMO_SIM"]
    requests = build_requests(["DEMO_SIM"])
    assert len(requests) == 6 * 5
    assert {r.lead_days for r in requests} == {1, 7, 15, 30, 45}
    for r in requests:
        assert r.travel_date - timedelta(days=r.lead_days) == requests[0].travel_date - timedelta(days=requests[0].lead_days)


@pytest.mark.asyncio
async def test_daily_collection_runs_every_route_and_window_and_is_idempotent(db):
    first = await run_daily_collection(db, recompute_index=False)
    assert first["requests"] == 30
    assert first["failed"] == 0
    assert first["quotes_normalized"] > 0
    assert await db["scheduled_jobs"].count_documents({}) == 1

    repo = FlightQuoteRepository(db)
    eligible = {"quality.status": {"$in": [QualityStatus.VALIDATED.value, QualityStatus.PROVISIONAL.value]}}
    eligible_after_first = await repo.count(eligible)

    second = await run_daily_collection(db, recompute_index=False)
    # Re-running the same day never double-counts: every repeat is kept on
    # record (nothing deleted) but none of them is index-eligible.
    assert await repo.count({}) == first["quotes_normalized"] + second["quotes_normalized"]
    assert await repo.count(eligible) == eligible_after_first
    assert await repo.count({"quality.status": QualityStatus.DUPLICATE.value}) > 0
