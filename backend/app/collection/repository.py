"""Persistence for the collection pipeline: SearchRun, RawObservation,
FlightQuote, CollectionError - all via their MongoDB repositories
(``app.repositories.*``). Kept separate from adapters (which must never
touch the database) and from ``CollectionService`` (which decides *what*
to persist and when). This class only knows *how*, and only ever talks
to the database through the typed repositories - never raw collection
queries.
"""
import hashlib
import json
from datetime import datetime

from pymongo.asynchronous.database import AsyncDatabase

from app.core.enums import CollectionErrorType, DataProvenance, RawObservationStatus, SearchRunStatus
from app.db.bson_utils import date_to_datetime
from app.models.collection_error import CollectionErrorDocument
from app.models.raw_observation import RawObservationDocument
from app.models.search_run import SearchRunDocument
from app.repositories.collection_error_repository import CollectionErrorRepository
from app.repositories.flight_quote_repository import FlightQuoteRepository
from app.repositories.raw_observation_repository import RawObservationRepository
from app.repositories.search_run_repository import SearchRunRepository
from app.schemas.collection import CollectionError, CollectionRequest
from app.schemas.flight_quote import FlightQuoteCreate


def compute_payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CollectionRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.search_runs = SearchRunRepository(db)
        self.raw_observations = RawObservationRepository(db)
        self.flight_quotes = FlightQuoteRepository(db)
        self.collection_errors = CollectionErrorRepository(db)

    async def create_search_run(self, request: CollectionRequest, *, started_at: datetime) -> str:
        document = SearchRunDocument(
            source=request.source_id,
            origin=request.origin,
            destination=request.destination,
            route=f"{request.origin}-{request.destination}",
            travel_date=date_to_datetime(request.travel_date),
            lead_days=request.lead_days,
            status=SearchRunStatus.RUNNING,
            started_at=started_at,
        )
        return await self.search_runs.create(document)

    async def finalize_search_run(
        self,
        search_run_id: str,
        *,
        status: SearchRunStatus,
        completed_at: datetime,
        records_found: int,
        records_valid: int,
        error_message: str | None,
    ) -> None:
        await self.search_runs.finalize(
            search_run_id,
            status=status,
            completed_at=completed_at,
            records_found=records_found,
            records_valid=records_valid,
            error_message=error_message,
        )

    async def persist_raw_observation(
        self,
        *,
        search_run_id: str,
        source: str,
        request: CollectionRequest,
        raw_payload: dict,
        status: RawObservationStatus,
        provenance: DataProvenance,
        collected_at: datetime,
    ) -> str:
        document = RawObservationDocument(
            search_run_id=search_run_id,
            source=source,
            collected_at=collected_at,
            request_parameters=request.model_dump(mode="json"),
            raw_payload=raw_payload,
            payload_hash=compute_payload_hash(raw_payload),
            status=status,
            provenance=provenance,
        )
        return await self.raw_observations.create(document)

    async def mark_raw_observation_status(
        self,
        observation_id: str,
        status: RawObservationStatus,
        *,
        quality_status: str | None = None,
        quality_reason: str | None = None,
    ) -> None:
        await self.raw_observations.set_status(
            observation_id, status.value, quality_status=quality_status, quality_reason=quality_reason
        )

    async def persist_flight_quote(self, quote: FlightQuoteCreate) -> str:
        return await self.flight_quotes.create(quote)

    async def persist_error(self, *, search_run_id: str, source: str, error: CollectionError) -> None:
        document = CollectionErrorDocument(
            search_run_id=search_run_id,
            source=source,
            error_type=CollectionErrorType(error.error_type),
            message=error.message,
            detail=error.detail,
            retryable=error.retryable,
        )
        await self.collection_errors.create(document)
