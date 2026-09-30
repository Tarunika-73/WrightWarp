"""Repository for the ``flight_quotes`` collection.

The only place that maps between the flat, canonical
``app.schemas.flight_quote.FlightQuoteCreate``/``FlightQuoteRead`` (what
the collection pipeline and any API caller works with) and the nested
``app.models.flight_quote.FlightQuoteDocument`` (how it is actually
stored) - see that module's docstring for why the two shapes differ.
"""
from pymongo.asynchronous.database import AsyncDatabase

from app.core.enums import SourceType
from app.core.sources import get_source
from app.db.bson_utils import date_to_datetime, datetime_to_date
from app.db.object_id import to_object_id, to_str_id
from app.models.flight_quote import (
    AvailabilityInfo,
    FareAttributes,
    FareBreakdown,
    FlightInfo,
    FlightQuoteDocument,
    ProvenanceInfo,
    QualityInfo,
    RouteRef,
    SourceRef,
    TravelInfo,
)
from app.schemas.flight_quote import FlightQuoteCreate, FlightQuoteRead

COLLECTION_NAME = "flight_quotes"


def _to_document(quote: FlightQuoteCreate, source_type: SourceType) -> FlightQuoteDocument:
    return FlightQuoteDocument(
        search_run_id=quote.search_run_id,
        source=SourceRef(id=quote.source, type=source_type),
        route=RouteRef(origin=quote.origin, destination=quote.destination),
        travel=TravelInfo(
            travel_date=date_to_datetime(quote.travel_date),
            observation_date=date_to_datetime(quote.observation_date) if quote.observation_date else None,
            departure_datetime=quote.departure_datetime,
            arrival_datetime=quote.arrival_datetime,
            lead_days=quote.lead_days,
        ),
        flight=FlightInfo(
            airline_code=quote.airline_code, flight_number=quote.flight_number, stops=quote.stops
        ),
        fare=FareBreakdown(
            base_fare=quote.base_fare,
            taxes=quote.taxes,
            airport_charges=quote.airport_charges,
            user_development_fee=quote.user_development_fee,
            convenience_fee=quote.convenience_fee,
            fuel_surcharge=quote.fuel_surcharge,
            baggage_fee=quote.baggage_fee,
            seat_fee=quote.seat_fee,
            meal_fee=quote.meal_fee,
            other_fees=quote.other_fees,
            total_fare=quote.total_fare,
            currency=quote.currency,
            components_available=quote.components_available,
        ),
        fare_attributes=FareAttributes(
            cabin_class=quote.cabin_class,
            fare_family=quote.fare_family,
            refundable=quote.refundable,
            baggage_included=quote.baggage_included,
        ),
        availability=AvailabilityInfo(
            status=quote.availability_status, cancellation_status=quote.cancellation_status
        ),
        quality=QualityInfo(
            status=quote.quality_status,
            score=quote.quality_score,
            reason=quote.quality_reason,
            flags=quote.quality_flags,
            robust_z=quote.quality_robust_z,
            rules_version=quote.quality_rules_version,
        ),
        provenance=ProvenanceInfo(
            data_type=quote.provenance,
            collected_at=quote.search_datetime,
            raw_observation_id=quote.raw_observation_id,
            raw_quote_hash=quote.raw_quote_hash,
            normalization_version=quote.normalization_version,
            extraction_version=quote.extraction_version,
        ),
        dedup_key=quote.dedup_key,
    )


def _to_flat(doc: dict) -> dict:
    source, route, travel, flight, fare, fare_attrs, availability, quality, provenance = (
        doc["source"],
        doc["route"],
        doc["travel"],
        doc["flight"],
        doc["fare"],
        doc["fare_attributes"],
        doc["availability"],
        doc["quality"],
        doc["provenance"],
    )
    return {
        "id": to_str_id(doc["_id"]),
        "search_run_id": doc["search_run_id"],
        "source": source["id"],
        "airline_code": flight.get("airline_code"),
        "flight_number": flight.get("flight_number"),
        "origin": route["origin"],
        "destination": route["destination"],
        "departure_datetime": travel.get("departure_datetime"),
        "arrival_datetime": travel.get("arrival_datetime"),
        "travel_date": datetime_to_date(travel["travel_date"]),
        "search_datetime": provenance["collected_at"],
        "observation_date": datetime_to_date(travel["observation_date"]) if travel.get("observation_date") else None,
        "lead_days": travel["lead_days"],
        "cabin_class": fare_attrs["cabin_class"],
        "fare_family": fare_attrs.get("fare_family"),
        "stops": flight.get("stops"),
        "base_fare": fare.get("base_fare"),
        "taxes": fare.get("taxes"),
        "airport_charges": fare.get("airport_charges"),
        "user_development_fee": fare.get("user_development_fee"),
        "convenience_fee": fare.get("convenience_fee"),
        "fuel_surcharge": fare.get("fuel_surcharge"),
        "baggage_fee": fare.get("baggage_fee"),
        "seat_fee": fare.get("seat_fee"),
        "meal_fee": fare.get("meal_fee"),
        "other_fees": fare.get("other_fees"),
        "total_fare": fare.get("total_fare"),
        "currency": fare["currency"],
        "components_available": fare.get("components_available") or [],
        "availability_status": availability["status"],
        "cancellation_status": availability.get("cancellation_status"),
        "refundable": fare_attrs.get("refundable"),
        "baggage_included": fare_attrs.get("baggage_included"),
        "raw_quote_hash": provenance.get("raw_quote_hash"),
        "raw_observation_id": provenance.get("raw_observation_id"),
        "provenance": provenance["data_type"],
        "quality_status": quality["status"],
        "quality_score": quality.get("score"),
        "quality_reason": quality.get("reason"),
        "quality_flags": quality.get("flags") or [],
        "quality_robust_z": quality.get("robust_z"),
        "quality_rules_version": quality.get("rules_version"),
        "dedup_key": doc.get("dedup_key"),
        "normalization_version": provenance.get("normalization_version"),
        "extraction_version": provenance.get("extraction_version"),
        "created_at": doc["created_at"],
    }


class FlightQuoteRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.collection = db[COLLECTION_NAME]

    async def create(self, quote: FlightQuoteCreate) -> str:
        source_type = get_source(quote.source).source_type
        document = _to_document(quote, source_type)
        result = await self.collection.insert_one(document.model_dump(exclude={"id"}))
        return to_str_id(result.inserted_id)

    async def get(self, quote_id: str) -> FlightQuoteRead | None:
        doc = await self.collection.find_one({"_id": to_object_id(quote_id)})
        if doc is None:
            return None
        return FlightQuoteRead(**_to_flat(doc))

    async def find_by_search_run(self, search_run_id: str) -> list[FlightQuoteRead]:
        docs = [doc async for doc in self.collection.find({"search_run_id": search_run_id})]
        return [FlightQuoteRead(**_to_flat(doc)) for doc in docs]

    async def find_by_route(self, origin: str, destination: str, *, limit: int = 100) -> list[FlightQuoteRead]:
        cursor = self.collection.find({"route.origin": origin, "route.destination": destination}).limit(limit)
        docs = [doc async for doc in cursor]
        return [FlightQuoteRead(**_to_flat(doc)) for doc in docs]

    async def count_by_search_run(self, search_run_id: str) -> int:
        return await self.collection.count_documents({"search_run_id": search_run_id})

    async def insert_many(self, quotes: list[FlightQuoteCreate]) -> list[str]:
        """Bulk insert (used by the demo backfill). Same mapping as ``create``."""
        if not quotes:
            return []
        documents = [_to_document(q, get_source(q.source).source_type).model_dump(exclude={"id"}) for q in quotes]
        result = await self.collection.insert_many(documents, ordered=False)
        return [to_str_id(i) for i in result.inserted_ids]

    async def dedup_key_exists(self, dedup_key: str) -> bool:
        return await self.collection.count_documents({"dedup_key": dedup_key}, limit=1) > 0

    async def search(self, query: dict, *, skip: int = 0, limit: int = 50, sort: list | None = None) -> list[FlightQuoteRead]:
        cursor = self.collection.find(query).sort(sort or [("travel.observation_date", -1), ("_id", -1)]).skip(skip).limit(limit)
        return [FlightQuoteRead(**_to_flat(doc)) async for doc in cursor]

    async def count(self, query: dict) -> int:
        return await self.collection.count_documents(query)

    async def aggregate(self, pipeline: list[dict]) -> list[dict]:
        cursor = await self.collection.aggregate(pipeline, allowDiskUse=True)
        return [doc async for doc in cursor]

    async def ensure_indexes(self) -> None:
        await self.collection.create_index(
            [("route.origin", 1), ("route.destination", 1), ("travel.travel_date", 1), ("travel.lead_days", 1)]
        )
        await self.collection.create_index([("travel.observation_date", 1), ("quality.status", 1)])
        await self.collection.create_index(
            [("route.origin", 1), ("route.destination", 1), ("travel.observation_date", -1)]
        )
        await self.collection.create_index("dedup_key")
        await self.collection.create_index("search_run_id")
        await self.collection.create_index([("created_at", -1)])
        await self.collection.create_index([("availability.status", 1), ("quality.status", 1)])
