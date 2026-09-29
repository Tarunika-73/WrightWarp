from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_db
from app.core.config import get_settings
from app.db.indexes import ensure_indexes
from app.main import app
from app.repositories.source_repository import SourceRepository

TEST_DB_NAME = "wrightwarp_test"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
async def db() -> AsyncDatabase:
    """An isolated MongoDB database, dropped after the test.

    Never the developer's real database (``wrightwarp`` by default) - a
    dedicated client connects to ``wrightwarp_test`` instead, and the whole
    database is dropped in teardown regardless of what the test wrote.
    Indexes and the source registry are set up first so tests see the same
    ready state the real app would have after startup.
    """
    settings = get_settings()
    client_ = AsyncMongoClient(settings.mongo_connection_uri)
    database = client_[TEST_DB_NAME]
    await ensure_indexes(database)
    await SourceRepository(database).sync_registry()
    try:
        yield database
    finally:
        await client_.drop_database(TEST_DB_NAME)
        await client_.close()


@pytest.fixture
def client_with_db(db: AsyncDatabase) -> TestClient:
    """A TestClient whose ``get_db`` dependency is the isolated test ``db``.

    Note: constructing ``TestClient(app)`` still runs the real app lifespan
    (connects to the *developer's* configured MongoDB, syncs the source
    registry, ensures indexes) exactly as it would in production - that is
    idempotent metadata only, never test data. Every actual read/write the
    tests perform goes through this dependency override, into the isolated
    ``db`` above.
    """
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def travel_date() -> date:
    return date(2026, 1, 8)
