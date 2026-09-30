"""Adapter for the simulated demo market (``DEMO_SIM``) - DEMO DATA ONLY.

Makes no network calls. Serves "today's" (IST) simulated fares for the
requested route and booking window, so the scheduled daily collection
exercises the complete live pipeline (compliance gate, rate limiter,
raw observation, normalization, quality engine, persistence) without
touching any real website. Registered only in demo mode.
"""
from datetime import datetime, timezone

from app.collection.errors import CollectionException
from app.core.enums import CollectionErrorType, RawObservationStatus
from app.demo.market import SIM_SOURCE_ID, generate_observations
from app.normalization.fares import observation_date
from app.schemas.collection import AdapterObservation, AdapterSearchOutcome, CollectionRequest


class SimulatedMarketAdapter:
    """``SourceAdapter`` over ``app.demo.market``. See ``app.collection.adapters.base.SourceAdapter``."""

    @property
    def source_id(self) -> str:
        return SIM_SOURCE_ID

    async def search(self, request: CollectionRequest) -> AdapterSearchOutcome:
        route = f"{request.origin}-{request.destination}"
        today_ist = observation_date(datetime.now(timezone.utc))
        if (request.travel_date - today_ist).days != request.lead_days:
            raise CollectionException(
                CollectionErrorType.INVALID_REQUEST,
                "DEMO_SIM only serves searches made today: travel_date must equal today (IST) + lead_days",
            )
        payloads = generate_observations(route, today_ist, request.lead_days)
        return AdapterSearchOutcome(
            observations=[AdapterObservation(raw_payload=p, status=RawObservationStatus.COLLECTED) for p in payloads],
        )
