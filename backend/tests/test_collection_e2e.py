"""End-to-end pipeline test.

CollectionRequest -> MockSourceAdapter -> RawObservation -> normalization ->
quality engine -> FlightQuote -> MongoDB. Verifies a synthetic flight quote
travels through the entire framework and that its provenance is never
anything but SYNTHETIC.
"""
from datetime import date, timedelta

import pytest

from app.collection.service import CollectionService
from app.core.enums import CollectionOutcome, DataProvenance, QualityStatus, RawObservationStatus, SearchRunStatus
from app.repositories.flight_quote_repository import FlightQuoteRepository
from app.repositories.raw_observation_repository import RawObservationRepository
from app.repositories.search_run_repository import SearchRunRepository
from app.schemas.collection import CollectionRequest


def _request() -> CollectionRequest:
    return CollectionRequest(
        source_id="MOCK",
        origin="DEL",
        destination="BOM",
        travel_date=date.today() + timedelta(days=15),
        lead_days=15,
    )


@pytest.mark.asyncio
async def test_synthetic_flight_quote_travels_the_full_pipeline(db):
    request = _request()
    result = await CollectionService(db).run(request)

    # 1. CollectionResult reports a clean success.
    assert result.success is True
    assert result.outcome == CollectionOutcome.SUCCESS
    assert result.search_run_id is not None

    # 2. SearchRun (the audit anchor) was persisted with a terminal SUCCESS status.
    run = await SearchRunRepository(db).get_by_id(result.search_run_id)
    assert run["status"] == SearchRunStatus.SUCCESS.value
    assert run["source"] == "MOCK"
    assert run["route"] == "DEL-BOM"
    assert run["lead_days"] == 15

    # 3. Exactly one RawObservation, tagged SYNTHETIC, marked NORMALIZED, carrying its quality decision.
    raws = await RawObservationRepository(db).find_by_search_run(result.search_run_id)
    assert len(raws) == 1
    raw = raws[0]
    assert raw["provenance"] == DataProvenance.SYNTHETIC.value
    assert raw["status"] == RawObservationStatus.NORMALIZED.value
    assert raw["raw_payload"]["provenance"] == "SYNTHETIC"
    assert raw["quality_status"] in (QualityStatus.VALIDATED.value, QualityStatus.PROVISIONAL.value)

    # 4. Exactly one FlightQuote, traceable back to the same SearchRun and RawObservation.
    quotes = await FlightQuoteRepository(db).find_by_search_run(result.search_run_id)
    assert len(quotes) == 1
    quote = quotes[0]
    assert quote.provenance == DataProvenance.SYNTHETIC.value
    assert quote.source == "MOCK"
    assert quote.travel_date == request.travel_date
    assert quote.lead_days == 15
    assert quote.total_fare is not None
    assert quote.raw_observation_id == raw["_id"]
    assert quote.raw_quote_hash == raw["payload_hash"]
    assert quote.dedup_key
    assert quote.observation_date is not None
    assert quote.normalization_version

    # 5. The synthetic quote is never presented as REAL data anywhere in the chain.
    assert DataProvenance.REAL.value not in (raw["provenance"], quote.provenance)


@pytest.mark.asyncio
async def test_repeating_a_collection_marks_the_second_quote_duplicate(db):
    service = CollectionService(db)
    first = await service.run(_request())
    second = await service.run(_request())

    q1 = (await FlightQuoteRepository(db).find_by_search_run(first.search_run_id))[0]
    q2 = (await FlightQuoteRepository(db).find_by_search_run(second.search_run_id))[0]
    assert q1.quality_status != QualityStatus.DUPLICATE.value
    assert q2.quality_status == QualityStatus.DUPLICATE.value
    # Nothing was deleted: both observations remain on record with the same identity.
    assert q1.dedup_key == q2.dedup_key
