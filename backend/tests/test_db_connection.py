import pytest

import app.db.mongodb as mongodb_module
from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database, ping

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
    assert await ping() is False


@pytest.mark.asyncio
async def test_get_database_requires_a_connected_client(monkeypatch):
    monkeypatch.setattr(mongodb_module, "_client", None)
    with pytest.raises(RuntimeError):
        get_database()


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
