from datetime import date, timedelta

import pytest

from app.collection.adapters.mock import MockSourceAdapter
from app.schemas.collection import CollectionRequest


def _request(**overrides):
    payload = dict(
        source_id="MOCK",
        origin="DEL",
        destination="BOM",
        travel_date=date.today() + timedelta(days=15),
        lead_days=15,
    )
    payload.update(overrides)
    return CollectionRequest(**payload)


@pytest.mark.asyncio
async def test_mock_adapter_source_id():
    assert MockSourceAdapter().source_id == "MOCK"


@pytest.mark.asyncio
async def test_mock_adapter_returns_one_observation():
    outcome = await MockSourceAdapter().search(_request())
    assert len(outcome.observations) == 1
    assert outcome.errors == []
    assert outcome.blocked is False


@pytest.mark.asyncio
async def test_mock_adapter_is_deterministic():
    request = _request()
    first = await MockSourceAdapter().search(request)
    second = await MockSourceAdapter().search(request)
    assert first.observations[0].raw_payload == second.observations[0].raw_payload


@pytest.mark.asyncio
async def test_mock_adapter_payload_is_marked_synthetic():
    outcome = await MockSourceAdapter().search(_request())
    payload = outcome.observations[0].raw_payload
    assert payload["provenance"] == "SYNTHETIC"


@pytest.mark.asyncio
async def test_mock_adapter_payload_reflects_request():
    request = _request(origin="BOM", destination="DEL", lead_days=30)
    outcome = await MockSourceAdapter().search(request)
    payload = outcome.observations[0].raw_payload
    assert payload["origin"] == "BOM"
    assert payload["destination"] == "DEL"
    assert payload["lead_days"] == 30
