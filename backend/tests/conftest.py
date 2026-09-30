from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient, MongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.routes import AIRPORTS
from app.core.sources import list_sources
from app.db.indexes import ensure_indexes
from app.db.mongodb import get_database
from app.main import app
from app.repositories.source_repository import SourceRepository
from app.repositories.source_repository import _to_document as source_document

# Never the developer's real database (``wrightwarp`` by default): every
# test that reads or writes data goes to this database, which is dropped
# after each test regardless of what the test wrote.
TEST_DB_NAME = "wrightwarp_test"


def _sync_client() -> MongoClient:
    return MongoClient(get_settings().mongo_connection_uri, serverSelectionTimeoutMS=15_000)


def _clear_sync(client: MongoClient) -> None:
    # Drop collections one by one: a least-privilege Atlas user (readWrite)
    # may not hold the dropDatabase action.
    database = client[TEST_DB_NAME]
    for name in database.list_collection_names():
        database.drop_collection(name)


async def _clear_async(client: AsyncMongoClient) -> None:
    database = client[TEST_DB_NAME]
    for name in await database.list_collection_names():
        await database.drop_collection(name)


@pytest.fixture
def client() -> TestClient:
    # Used as a context manager so the app lifespan runs on the TestClient's
    # own event loop - the Mongo client is bound to that loop.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def db() -> AsyncDatabase:
    """An isolated MongoDB database on the test's event loop, dropped after the test.

    Indexes and the source registry are set up first so tests see the same
    ready state the real app would have after startup.
    """
    settings = get_settings()
    client_ = AsyncMongoClient(settings.mongo_connection_uri)
    await _clear_async(client_)  # in case a previous run was interrupted
    database = client_[TEST_DB_NAME]
    await ensure_indexes(database)
    await SourceRepository(database).sync_registry()
    try:
        yield database
    finally:
        await _clear_async(client_)
        await client_.close()


@pytest.fixture
def db_session(db: AsyncDatabase) -> AsyncDatabase:
    """Phase 1/2 name for the isolated test database (kept so older tests read naturally)."""
    return db


@pytest.fixture
def client_with_db() -> TestClient:
    """A TestClient whose ``get_db`` dependency points at the isolated test database.

    The override resolves the database through the app's own (loop-aware)
    Mongo client, so every request runs on the TestClient's event loop.
    Constructing the client still runs the real app lifespan against the
    developer's configured database - idempotent metadata only (indexes,
    registry mirror), never test data.
    """
    sync = _sync_client()
    sync[TEST_DB_NAME]["sources"].delete_many({})
    for definition in list_sources():
        sync[TEST_DB_NAME]["sources"].insert_one(source_document(definition))
    app.dependency_overrides[get_db] = lambda: get_database(TEST_DB_NAME)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        _clear_sync(sync)
        sync.close()


@pytest.fixture
def seed_airports() -> None:
    """Airport master data in the test database (collection itself no longer needs it)."""
    sync = _sync_client()
    for airport in AIRPORTS:
        sync[TEST_DB_NAME]["airports"].update_one(
            {"iata_code": airport.iata_code}, {"$set": {"name": airport.name, "city": airport.city, "state": airport.state, "active": True}}, upsert=True
        )
    sync.close()


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def travel_date() -> date:
    return date(2026, 1, 8)
