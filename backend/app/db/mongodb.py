"""Application-level MongoDB client lifecycle.

One ``AsyncMongoClient`` is created at FastAPI startup (see
``app.main``'s lifespan) and reused for every request - PyMongo's async
client already pools connections internally, so creating a new client
per request would only throw that pooling away and add connect latency
to every call. ``close_mongo_connection`` releases it at shutdown.

Uses PyMongo's native async API (``pymongo.AsyncMongoClient``, stable
since PyMongo 4.9) rather than Motor: Motor is now in maintenance mode
in favor of this built-in async support, so there is no reason to add a
second driver dependency.
"""
import logging

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.core.config import get_settings

logger = logging.getLogger("app.db.mongodb")

_client: AsyncMongoClient | None = None


async def connect_to_mongo() -> None:
    global _client
    settings = get_settings()
    _client = AsyncMongoClient(settings.mongo_connection_uri)
    # Force a round-trip now rather than on the first request, so a
    # misconfigured connection fails loudly at startup.
    await _client.admin.command("ping")
    logger.info("mongodb_connected db=%s", settings.mongo_db_name)


async def close_mongo_connection() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
        logger.info("mongodb_disconnected")


def get_database(db_name: str | None = None) -> AsyncDatabase:
    if _client is None:
        raise RuntimeError("MongoDB client is not connected - call connect_to_mongo() first")
    settings = get_settings()
    return _client[db_name or settings.mongo_db_name]


async def ping() -> bool:
    """Used by the health check. Returns False instead of raising on any failure."""
    if _client is None:
        return False
    try:
        await _client.admin.command("ping")
        return True
    except PyMongoError:
        logger.exception("mongodb_ping_failed")
        return False
