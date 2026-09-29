"""Coordinates one collection attempt end-to-end.

Pipeline: validate request -> look up source -> compliance check -> rate
limiter -> adapter -> raw observation -> normalization -> persistence.
This class contains no statistics or index logic (Phase 3+); its only job
is to run one (or a batch of) ``CollectionRequest`` and leave an
auditable trail behind.
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from pydantic import ValidationError
from pymongo.asynchronous.database import AsyncDatabase

from app.collection.adapters.registry import AdapterRegistry, adapter_registry
from app.collection.errors import CollectionException
from app.collection.normalizer import NormalizationError, normalize
from app.collection.rate_limiter import RateLimiter
from app.collection.repository import CollectionRepository
from app.core.enums import (
    CollectionErrorType,
    CollectionOutcome,
    DataProvenance,
    RawObservationStatus,
    SearchRunStatus,
    SourceStatus,
)
from app.core.sources import SourceDefinition, get_source
from app.schemas.collection import CollectionError, CollectionRequest, CollectionResult

logger = logging.getLogger("app.collection")

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 1.0


def _log(event: str, **fields: object) -> None:
    rendered = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("%s %s", event, rendered)


class CollectionService:
    def __init__(
        self,
        db: AsyncDatabase,
        *,
        adapters: AdapterRegistry = adapter_registry,
        rate_limiter: RateLimiter | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.repository = CollectionRepository(db)
        self.adapters = adapters
        self.rate_limiter = rate_limiter or RateLimiter()
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep

    async def run(self, request: CollectionRequest) -> CollectionResult:
        started_at = datetime.now(timezone.utc)
        route = f"{request.origin}-{request.destination}"
        search_run_id = await self.repository.create_search_run(request, started_at=started_at)
        _log("collection_started", source=request.source_id, route=route, lead_days=request.lead_days)

        try:
            source_def = get_source(request.source_id)
        except ValueError:
            return await self._finish(
                search_run_id,
                request,
                started_at,
                outcome=CollectionOutcome.FAILED,
                success=False,
                errors=[CollectionError(error_type=CollectionErrorType.INVALID_REQUEST, message=f"Unknown source_id: {request.source_id}")],
            )

        compliance_error = self._check_compliance(source_def)
        if compliance_error is not None:
            return await self._finish(search_run_id, request, started_at, outcome=CollectionOutcome.BLOCKED, success=False, errors=[compliance_error])

        adapter = self.adapters.get(source_def.source_id)
        if adapter is None:
            error = CollectionError(
                error_type=CollectionErrorType.SOURCE_UNAVAILABLE,
                message=f"No adapter registered for source_id={source_def.source_id}",
            )
            return await self._finish(search_run_id, request, started_at, outcome=CollectionOutcome.FAILED, success=False, errors=[error])

        adapter_outcome, attempt_errors, retry_warnings = await self._search_with_retries(adapter, request, source_def)

        if adapter_outcome is None:
            return await self._finish(search_run_id, request, started_at, outcome=CollectionOutcome.FAILED, success=False, errors=attempt_errors, warnings=retry_warnings)

        if adapter_outcome.blocked:
            block_error = CollectionError(
                error_type=CollectionErrorType.COMPLIANCE_BLOCKED,
                message=f"Source {source_def.source_id} signaled a compliance block at runtime",
            )
            return await self._finish(search_run_id, request, started_at, outcome=CollectionOutcome.BLOCKED, success=False, errors=[block_error], warnings=retry_warnings)

        all_errors = list(adapter_outcome.errors)

        if not adapter_outcome.observations:
            return await self._finish(
                search_run_id,
                request,
                started_at,
                outcome=CollectionOutcome.NO_RESULTS,
                success=True,
                errors=all_errors,
                warnings=retry_warnings,
            )

        provenance = DataProvenance.SYNTHETIC if source_def.source_id == "MOCK" else DataProvenance.REAL
        raw_count = 0
        normalized_count = 0
        completed_at = datetime.now(timezone.utc)

        for obs in adapter_outcome.observations:
            raw_observation_id = await self.repository.persist_raw_observation(
                search_run_id=search_run_id,
                source=source_def.source_id,
                request=request,
                raw_payload=obs.raw_payload,
                status=obs.status,
                provenance=provenance,
                collected_at=completed_at,
            )
            raw_count += 1
            try:
                quote = normalize(
                    search_run_id=search_run_id,
                    source=source_def.source_id,
                    request=request,
                    raw_payload=obs.raw_payload,
                    provenance=provenance,
                    search_datetime=started_at,
                    raw_observation_id=raw_observation_id,
                )
                await self.repository.persist_flight_quote(quote)
                normalized_count += 1
                await self.repository.mark_raw_observation_status(raw_observation_id, RawObservationStatus.NORMALIZED)
            except (NormalizationError, ValidationError) as exc:
                await self.repository.mark_raw_observation_status(raw_observation_id, RawObservationStatus.PARSE_FAILED)
                all_errors.append(CollectionError(error_type=CollectionErrorType.PARSER_ERROR, message=str(exc)))

        outcome = (
            CollectionOutcome.SUCCESS
            if normalized_count == raw_count and not all_errors
            else CollectionOutcome.PARTIAL
        )

        return await self._finish(
            search_run_id,
            request,
            started_at,
            outcome=outcome,
            success=True,
            errors=all_errors,
            warnings=retry_warnings,
            completed_at=completed_at,
            records_found=raw_count,
            raw_observations_persisted=raw_count,
            quotes_normalized=normalized_count,
        )

    async def run_batch(self, requests: list[CollectionRequest]) -> list[CollectionResult]:
        """Run several requests independently - one failure never affects another's status."""
        results: list[CollectionResult] = []
        for request in requests:
            try:
                result = await self.run(request)
            except Exception:  # noqa: BLE001 - a batch item must never take the rest down with it
                logger.exception("collection_batch_item_crashed source=%s", request.source_id)
                now = datetime.now(timezone.utc)
                result = CollectionResult(
                    success=False,
                    outcome=CollectionOutcome.FAILED,
                    source=request.source_id,
                    request=request,
                    started_at=now,
                    completed_at=now,
                    errors=[CollectionError(error_type=CollectionErrorType.UNKNOWN_ERROR, message="Unhandled service error")],
                )
            results.append(result)
        return results

    async def _search_with_retries(self, adapter, request: CollectionRequest, source_def: SourceDefinition):
        """Retry only transient (``CollectionException.retryable``) failures.

        A retry that eventually succeeds leaves no trace in ``errors`` (so a
        recovered hiccup does not taint an otherwise-SUCCESS outcome as
        PARTIAL) - it is recorded in ``warnings`` instead, for the audit trail.
        """
        warnings: list[str] = []
        attempt = 0
        while attempt < self.max_attempts:
            attempt += 1
            await self.rate_limiter.acquire(source_def.source_id, source_def.rate_limit_per_minute)
            try:
                outcome = await adapter.search(request)
                return outcome, [], warnings
            except CollectionException as exc:
                if not exc.retryable or attempt >= self.max_attempts:
                    error = CollectionError(error_type=exc.error_type, message=exc.message, detail=exc.detail, retryable=exc.retryable)
                    return None, [error], warnings
                warnings.append(f"attempt {attempt} failed ({exc.error_type}: {exc.message}); retrying")
                await self._sleep(self.backoff_seconds * (2 ** (attempt - 1)))
            except Exception:  # noqa: BLE001 - never let an adapter bug crash the service
                logger.exception("collection_adapter_unhandled_error source=%s", source_def.source_id)
                error = CollectionError(error_type=CollectionErrorType.UNKNOWN_ERROR, message="Unhandled adapter error")
                return None, [error], warnings
        return None, [], warnings  # pragma: no cover - loop always returns above

    @staticmethod
    def _check_compliance(source_def: SourceDefinition) -> CollectionError | None:
        if not source_def.enabled or source_def.status != SourceStatus.IMPLEMENTED:
            return CollectionError(
                error_type=CollectionErrorType.COMPLIANCE_BLOCKED,
                message=(
                    f"Source {source_def.source_id} is not cleared for collection "
                    f"(status={source_def.status}, enabled={source_def.enabled})"
                ),
                detail=source_def.notes,
            )
        return None

    _OUTCOME_TO_RUN_STATUS = {
        CollectionOutcome.SUCCESS: SearchRunStatus.SUCCESS,
        CollectionOutcome.PARTIAL: SearchRunStatus.PARTIAL,
        CollectionOutcome.FAILED: SearchRunStatus.FAILED,
        CollectionOutcome.BLOCKED: SearchRunStatus.BLOCKED,
        CollectionOutcome.NO_RESULTS: SearchRunStatus.NO_RESULTS,
    }

    async def _finish(
        self,
        search_run_id: str,
        request: CollectionRequest,
        started_at: datetime,
        *,
        outcome: CollectionOutcome,
        success: bool,
        errors: list[CollectionError],
        warnings: list[str] | None = None,
        completed_at: datetime | None = None,
        records_found: int = 0,
        raw_observations_persisted: int = 0,
        quotes_normalized: int = 0,
    ) -> CollectionResult:
        completed_at = completed_at or datetime.now(timezone.utc)
        error_message = "; ".join(e.message for e in errors) or None
        await self.repository.finalize_search_run(
            search_run_id,
            status=self._OUTCOME_TO_RUN_STATUS[outcome],
            completed_at=completed_at,
            records_found=records_found,
            records_valid=quotes_normalized,
            error_message=error_message,
        )
        for error in errors:
            await self.repository.persist_error(search_run_id=search_run_id, source=request.source_id, error=error)

        route = f"{request.origin}-{request.destination}"
        duration = (completed_at - started_at).total_seconds()
        event = {
            CollectionOutcome.FAILED: "collection_failed",
            CollectionOutcome.BLOCKED: "collection_blocked",
        }.get(outcome, "collection_completed")
        log_fn = logger.warning if outcome in (CollectionOutcome.FAILED, CollectionOutcome.BLOCKED) else logger.info
        error_types = ",".join(sorted({e.error_type for e in errors})) or "none"
        log_fn(
            "%s source=%s route=%s lead_days=%s duration_s=%.3f records_found=%s records_persisted=%s error_type=%s",
            event,
            request.source_id,
            route,
            request.lead_days,
            duration,
            records_found,
            quotes_normalized,
            error_types,
        )

        return CollectionResult(
            search_run_id=search_run_id,
            success=success,
            outcome=outcome,
            source=request.source_id,
            request=request,
            started_at=started_at,
            completed_at=completed_at,
            records_found=records_found,
            raw_observations_persisted=raw_observations_persisted,
            quotes_normalized=quotes_normalized,
            errors=errors,
            warnings=warnings or [],
        )
