"""Creates every index this project actually queries by, once, at startup.

``create_index`` is idempotent (a no-op if the index already exists with
the same spec), so calling this on every startup is safe. See
``docs/architecture/database.md`` for why each index was chosen -
deliberately not "one index per field."
"""
from pymongo.asynchronous.database import AsyncDatabase

from app.repositories import (
    AirlineRepository,
    AirportRepository,
    CollectionErrorRepository,
    FlightQuoteRepository,
    RawObservationRepository,
    RouteRepository,
    SearchRunRepository,
    SourceRepository,
)


async def ensure_indexes(db: AsyncDatabase) -> None:
    await SourceRepository(db).ensure_indexes()
    await AirlineRepository(db).ensure_indexes()
    await AirportRepository(db).ensure_indexes()
    await RouteRepository(db).ensure_indexes()
    await SearchRunRepository(db).ensure_indexes()
    await RawObservationRepository(db).ensure_indexes()
    await FlightQuoteRepository(db).ensure_indexes()
    await CollectionErrorRepository(db).ensure_indexes()
