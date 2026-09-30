from datetime import date, timedelta

import pytest

from app.collection.service import CollectionService
from app.repositories.flight_quote_repository import FlightQuoteRepository
from app.repositories.raw_observation_repository import RawObservationRepository
from app.repositories.search_run_repository import SearchRunRepository
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
async def test_search_run_is_created(db):
    result = await CollectionService(db).run(_request())
    run = await SearchRunRepository(db).get_by_id(result.search_run_id)
    assert run is not None
    assert run["source"] == "MOCK"
    assert run["route"] == "DEL-BOM"


@pytest.mark.asyncio
async def test_raw_observation_links_to_search_run(db):
    result = await CollectionService(db).run(_request())
    raws = await RawObservationRepository(db).find_by_search_run(result.search_run_id)
    assert len(raws) == 1
    assert raws[0]["source"] == "MOCK"
    assert raws[0]["payload_hash"]


@pytest.mark.asyncio
async def test_flight_quote_links_to_search_run(db):
    result = await CollectionService(db).run(_request())
    quotes = await FlightQuoteRepository(db).find_by_search_run(result.search_run_id)
    assert len(quotes) == 1
    assert quotes[0].source == "MOCK"
    assert quotes[0].provenance == "SYNTHETIC"


@pytest.mark.asyncio
async def test_raw_observation_and_flight_quote_share_search_run(db):
    result = await CollectionService(db).run(_request())
    raw = (await RawObservationRepository(db).find_by_search_run(result.search_run_id))[0]
    quote = (await FlightQuoteRepository(db).find_by_search_run(result.search_run_id))[0]
    assert raw["search_run_id"] == quote.search_run_id
    assert quote.raw_observation_id == raw["_id"]
