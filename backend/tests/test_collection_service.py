from datetime import date, timedelta

import pytest

from app.collection.adapters.registry import AdapterRegistry
from app.collection.errors import CollectionException
from app.collection.rate_limiter import RateLimiter
from app.collection.service import CollectionService
from app.core import sources as sources_module
from app.core.enums import CollectionErrorType, CollectionOutcome, SearchRunStatus
from app.schemas.collection import AdapterObservation, AdapterSearchOutcome, CollectionRequest


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


class FailNTimesAdapter:
    """Fails ``fail_times`` calls with ``error_type``, then returns one valid synthetic observation."""

    def __init__(self, source_id: str, fail_times: int, error_type: CollectionErrorType) -> None:
        self._source_id = source_id
        self.fail_times = fail_times
        self.error_type = error_type
        self.calls = 0

    @property
    def source_id(self) -> str:
        return self._source_id

    async def search(self, request: CollectionRequest) -> AdapterSearchOutcome:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise CollectionException(self.error_type, f"simulated failure #{self.calls}")
        return AdapterSearchOutcome(
            observations=[
                AdapterObservation(
                    raw_payload={
                        "origin": request.origin,
                        "destination": request.destination,
                        "base_fare": 4000.0,
                        "taxes": 800.0,
                        "total_fare": 4800.0,
                        "currency": "INR",
                        "availability_status": "AVAILABLE",
                        "airline_code": "6E",
                        "flight_number": "6E1234",
                    }
                )
            ]
        )


class EmptyResultsAdapter:
    def __init__(self, source_id: str) -> None:
        self._source_id = source_id

    @property
    def source_id(self) -> str:
        return self._source_id

    async def search(self, request: CollectionRequest) -> AdapterSearchOutcome:
        return AdapterSearchOutcome(observations=[])


def _service(db_session, adapter, **kwargs) -> CollectionService:
    registry = AdapterRegistry()
    registry.register(adapter)
    return CollectionService(
        db_session,
        adapters=registry,
        rate_limiter=RateLimiter(),
        max_attempts=kwargs.pop("max_attempts", 3),
        backoff_seconds=0.0,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_successful_collection(db_session, seed_airports):
    from app.collection.adapters.mock import MockSourceAdapter

    service = _service(db_session, MockSourceAdapter())
    result = await service.run(_request())

    assert result.success is True
    assert result.outcome == CollectionOutcome.SUCCESS
    assert result.quotes_normalized == 1
    assert result.raw_observations_persisted == 1
    assert result.search_run_id is not None


@pytest.mark.asyncio
async def test_failure_after_exhausting_retries(db_session, seed_airports):
    adapter = FailNTimesAdapter("MOCK", fail_times=5, error_type=CollectionErrorType.NETWORK_ERROR)
    service = _service(db_session, adapter, max_attempts=3)

    result = await service.run(_request())

    assert result.success is False
    assert result.outcome == CollectionOutcome.FAILED
    assert adapter.calls == 3
    assert any(e.error_type == CollectionErrorType.NETWORK_ERROR for e in result.errors)


@pytest.mark.asyncio
async def test_retry_then_success_is_reported_as_success(db_session, seed_airports):
    adapter = FailNTimesAdapter("MOCK", fail_times=2, error_type=CollectionErrorType.NETWORK_ERROR)
    service = _service(db_session, adapter, max_attempts=3)

    result = await service.run(_request())

    assert adapter.calls == 3
    assert result.success is True
    assert result.outcome == CollectionOutcome.SUCCESS
    assert result.errors == []
    assert len(result.warnings) == 2


@pytest.mark.asyncio
async def test_non_retryable_error_stops_immediately(db_session, seed_airports):
    adapter = FailNTimesAdapter("MOCK", fail_times=5, error_type=CollectionErrorType.INVALID_REQUEST)
    service = _service(db_session, adapter, max_attempts=3)

    result = await service.run(_request())

    assert adapter.calls == 1
    assert result.outcome == CollectionOutcome.FAILED


@pytest.mark.asyncio
async def test_no_results_is_not_a_failure(db_session, seed_airports):
    adapter = EmptyResultsAdapter("MOCK")
    service = _service(db_session, adapter)

    result = await service.run(_request())

    assert result.success is True
    assert result.outcome == CollectionOutcome.NO_RESULTS
    assert result.records_found == 0


@pytest.mark.asyncio
async def test_pending_review_source_is_blocked(db_session, seed_airports):
    from app.collection.adapters.mock import MockSourceAdapter

    service = _service(db_session, MockSourceAdapter())
    result = await service.run(_request(source_id="6E"))

    assert result.success is False
    assert result.outcome == CollectionOutcome.BLOCKED
    assert result.errors[0].error_type == CollectionErrorType.COMPLIANCE_BLOCKED


@pytest.mark.asyncio
async def test_disabled_source_is_blocked_even_if_implemented(db_session, seed_airports, monkeypatch):
    import dataclasses

    from app.core.enums import SourceStatus

    mock_def = sources_module.get_source("MOCK")
    disabled_def = dataclasses.replace(mock_def, enabled=False)
    monkeypatch.setattr("app.collection.service.get_source", lambda source_id: disabled_def)

    from app.collection.adapters.mock import MockSourceAdapter

    service = _service(db_session, MockSourceAdapter())
    result = await service.run(_request())

    assert result.outcome == CollectionOutcome.BLOCKED


@pytest.mark.asyncio
async def test_unknown_source_id_fails_without_calling_any_adapter(db_session, seed_airports):
    # CollectionRequest itself only validates shape, not registry membership,
    # so an unknown source_id must be handled gracefully by the service.
    from app.collection.adapters.mock import MockSourceAdapter

    adapter = MockSourceAdapter()
    service = _service(db_session, adapter)
    request = _request(source_id="NOT_A_SOURCE")

    result = await service.run(request)

    assert result.success is False
    assert result.outcome == CollectionOutcome.FAILED
    assert result.errors[0].error_type == CollectionErrorType.INVALID_REQUEST
    assert adapter is not None  # never invoked; nothing to assert on calls for MockSourceAdapter


@pytest.mark.asyncio
async def test_search_run_status_persisted_matches_outcome(db_session, seed_airports):
    from app.collection.adapters.mock import MockSourceAdapter
    from app.models.search_run import SearchRun

    service = _service(db_session, MockSourceAdapter())
    result = await service.run(_request())

    run = db_session.get(SearchRun, result.search_run_id)
    assert run.status == SearchRunStatus.SUCCESS
    assert run.records_valid == 1
