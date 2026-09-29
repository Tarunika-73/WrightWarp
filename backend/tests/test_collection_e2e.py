"""End-to-end Phase 2 pipeline test.

CollectionRequest -> MockSourceAdapter -> RawObservation -> Normalizer ->
FlightQuote -> PostgreSQL. Verifies a synthetic flight quote successfully
travels through the entire framework and that its provenance is never
anything but SYNTHETIC.
"""
from datetime import date, timedelta

import pytest

from app.collection.service import CollectionService
from app.core.enums import CollectionOutcome, DataProvenance, RawObservationStatus, SearchRunStatus
from app.models.flight_quote import FlightQuote
from app.models.raw_observation import RawObservation
from app.models.search_run import SearchRun
from app.schemas.collection import CollectionRequest


@pytest.mark.asyncio
async def test_synthetic_flight_quote_travels_the_full_pipeline(db_session, seed_airports):
    request = CollectionRequest(
        source_id="MOCK",
        origin="DEL",
        destination="BOM",
        travel_date=date.today() + timedelta(days=15),
        lead_days=15,
    )

    service = CollectionService(db_session)
    result = await service.run(request)

    # 1. CollectionResult reports a clean success.
    assert result.success is True
    assert result.outcome == CollectionOutcome.SUCCESS
    assert result.search_run_id is not None

    # 2. SearchRun (the audit anchor) was persisted with a terminal SUCCESS status.
    run = db_session.get(SearchRun, result.search_run_id)
    assert run is not None
    assert run.status == SearchRunStatus.SUCCESS
    assert run.source == "MOCK"
    assert run.route == "DEL-BOM"
    assert run.lead_days == 15

    # 3. Exactly one RawObservation was captured, tagged SYNTHETIC, and later marked NORMALIZED.
    raw_observations = db_session.query(RawObservation).filter(RawObservation.search_run_id == run.id).all()
    assert len(raw_observations) == 1
    raw = raw_observations[0]
    assert raw.provenance == DataProvenance.SYNTHETIC.value
    assert raw.status == RawObservationStatus.NORMALIZED.value
    assert raw.raw_payload["provenance"] == "SYNTHETIC"

    # 4. Exactly one FlightQuote was normalized from it, traceable back to the same SearchRun.
    quotes = db_session.query(FlightQuote).filter(FlightQuote.search_run_id == run.id).all()
    assert len(quotes) == 1
    quote = quotes[0]
    assert quote.provenance == DataProvenance.SYNTHETIC.value
    assert quote.source == "MOCK"
    assert quote.travel_date == request.travel_date
    assert quote.lead_days == 15
    assert quote.total_fare is not None

    # 5. The synthetic quote is never presented as REAL data anywhere in the chain.
    assert DataProvenance.REAL.value not in (raw.provenance, quote.provenance)
