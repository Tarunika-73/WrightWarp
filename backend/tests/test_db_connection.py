import pytest

import app.db.mongodb as mongodb_module
from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database, is_connected, ping

EXPECTED_COLLECTIONS = {
    "sources",
    "airlines",
    "airports",
    "routes",
    "search_runs",
    "raw_observations",
    "flight_quotes",
    "collection_errors",
}


@pytest.mark.asyncio
async def test_connect_ping_disconnect():
    await connect_to_mongo()
    try:
        assert await ping() is True
    finally:
        await close_mongo_connection()
    assert is_connected() is False


@pytest.mark.asyncio
async def test_get_database_connects_lazily(monkeypatch):
    # Serverless runtimes may not run the ASGI lifespan: the first
    # get_database() call must create the client instead of failing.
    monkeypatch.setattr(mongodb_module, "_client", None)
    monkeypatch.setattr(mongodb_module, "_client_loop", None)
    database = get_database()
    assert database.name
    assert is_connected() is True
    await close_mongo_connection()


@pytest.mark.asyncio
async def test_database_executes_a_command(db):
    result = await db.command("ping")
    assert result["ok"] == 1.0


@pytest.mark.asyncio
async def test_every_required_collection_is_writable(db):
    for name in EXPECTED_COLLECTIONS:
        await db[name].insert_one({"_smoke_test": True})
    collections = set(await db.list_collection_names())
    assert EXPECTED_COLLECTIONS.issubset(collections)
