"""Deterministic, synthetic-only adapter used to exercise the full pipeline.

This is the *only* adapter that may run before a real source clears
compliance review (see docs/architecture/source-adapters.md). It never
makes a network call and always returns the same shape of data for the
same request, so it can be used both as a development fixture and in
automated tests. Every observation it returns is unambiguously marked
``DataProvenance.SYNTHETIC`` by the normalizer - it must never be
mistaken for a real collected fare.
"""
from app.core.enums import RawObservationStatus
from app.schemas.collection import AdapterObservation, AdapterSearchOutcome, CollectionRequest

_BASE_FARE_INR = 4200.00
_TAXES_INR = 842.00
_FLIGHT_NUMBER = "6E1234"
_AIRLINE_CODE = "6E"


class MockSourceAdapter:
    """Synthetic ``SourceAdapter`` implementation. See ``app.collection.adapters.base.SourceAdapter``."""

    @property
    def source_id(self) -> str:
        return "MOCK"

    async def search(self, request: CollectionRequest) -> AdapterSearchOutcome:
        # Deterministic: the same (origin, destination, travel_date, lead_days)
        # always produces the same synthetic fare, so tests can assert on exact values.
        base_fare = _BASE_FARE_INR + (request.lead_days * 10)
        taxes = _TAXES_INR
        total_fare = round(base_fare + taxes, 2)

        payload = {
            "provenance": "SYNTHETIC",
            "source": self.source_id,
            "airline_code": _AIRLINE_CODE,
            "flight_number": _FLIGHT_NUMBER,
            "origin": request.origin,
            "destination": request.destination,
            "travel_date": request.travel_date.isoformat(),
            "lead_days": request.lead_days,
            "cabin_class": request.cabin_class,
            "passenger_count": request.passenger_count,
            "base_fare": base_fare,
            "taxes": taxes,
            "total_fare": total_fare,
            "currency": "INR",
            "availability_status": "AVAILABLE",
            "stops": 0,
        }

        return AdapterSearchOutcome(
            observations=[AdapterObservation(raw_payload=payload, status=RawObservationStatus.COLLECTED)],
            errors=[],
            blocked=False,
        )
