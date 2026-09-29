from datetime import date, timedelta

import pytest

from app.collection.adapters.mock import MockSourceAdapter
from app.collection.service import CollectionService
from app.models.flight_quote import FlightQuote
from app.models.raw_observation import RawObservation
from app.models.search_run import SearchRun
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
async def test_search_run_is_created(db_session, seed_airports):
    service = CollectionService(db_session)
    result = await service.run(_request())

    run = db_session.get(SearchRun, result.search_run_id)
    assert run is not None
    assert run.source == "MOCK"
    assert run.route == "DEL-BOM"


@pytest.mark.asyncio
async def test_raw_observation_links_to_search_run(db_session, seed_airports):
    service = CollectionService(db_session)
    result = await service.run(_request())

    raw_rows = db_session.query(RawObservation).filter(RawObservation.search_run_id == result.search_run_id).all()
    assert len(raw_rows) == 1
    assert raw_rows[0].source == "MOCK"
    assert raw_rows[0].payload_hash
    assert raw_rows[0].search_run.id == result.search_run_id


@pytest.mark.asyncio
async def test_flight_quote_links_to_search_run(db_session, seed_airports):
    service = CollectionService(db_session)
    result = await service.run(_request())

    quotes = db_session.query(FlightQuote).filter(FlightQuote.search_run_id == result.search_run_id).all()
    assert len(quotes) == 1
    assert quotes[0].source == "MOCK"
    assert quotes[0].provenance == "SYNTHETIC"


@pytest.mark.asyncio
async def test_raw_observation_and_flight_quote_share_search_run(db_session, seed_airports):
    service = CollectionService(db_session)
    result = await service.run(_request())

    raw = db_session.query(RawObservation).filter(RawObservation.search_run_id == result.search_run_id).one()
    quote = db_session.query(FlightQuote).filter(FlightQuote.search_run_id == result.search_run_id).one()
    assert raw.search_run_id == quote.search_run_id
