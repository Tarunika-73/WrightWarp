"""Application-level MongoDB client lifecycle.

One ``AsyncMongoClient`` is reused for every request - PyMongo's async
client already pools connections internally, so creating a new client
per request would only throw that pooling away and add connect latency
to every call. ``close_mongo_connection`` releases it at shutdown.

The client is created lazily and is *event-loop aware*: PyMongo's async
client is bound to the loop it was created on, and both serverless
runtimes (Vercel may not run the ASGI lifespan, and may run each
invocation on a fresh loop) and ``TestClient`` (one loop per client) can
hand us a different loop than the one a previous client was created on.
``get_database`` therefore (re)creates the client whenever the running
loop differs, instead of failing with "Cannot use AsyncMongoClient in
different event loop".

Uses PyMongo's native async API (``pymongo.AsyncMongoClient``, stable
since PyMongo 4.9) rather than Motor: Motor is now in maintenance mode
in favor of this built-in async support, so there is no reason to add a
second driver dependency.
"""
import asyncio
import logging

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.core.config import get_settings

logger = logging.getLogger("app.db.mongodb")

_client: AsyncMongoClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _new_client() -> AsyncMongoClient:
    settings = get_settings()
    # Never log the URI itself - it carries credentials.
    return AsyncMongoClient(
        settings.mongo_connection_uri,
        serverSelectionTimeoutMS=10_000,
        appname=settings.app_name,
        # Return timezone-aware (UTC) datetimes so API responses carry an offset.
        tz_aware=True,
    )


def _ensure_client() -> AsyncMongoClient:
    global _client, _client_loop
    loop = _running_loop()
    if _client is None or (loop is not None and _client_loop is not None and loop is not _client_loop):
        # A client bound to a dead/different loop cannot be closed from
        # this loop; dropping the reference lets it be garbage-collected.
        _client = _new_client()
        _client_loop = loop
    return _client


async def connect_to_mongo() -> None:
    client = _ensure_client()
    # Force a round-trip now rather than on the first request, so a
    # misconfigured connection fails loudly at startup.
    await client.admin.command("ping")
    logger.info("mongodb_connected db=%s", get_settings().mongo_db_name)


async def close_mongo_connection() -> None:
    global _client, _client_loop
    if _client is not None:
        client, _client, _client_loop = _client, None, None
        try:
            await client.close()
        except RuntimeError:  # pragma: no cover - client bound to another (closed) loop
            pass
        logger.info("mongodb_disconnected")


def get_database(db_name: str | None = None) -> AsyncDatabase:
    client = _ensure_client()
    return client[db_name or get_settings().mongo_db_name]


def is_connected() -> bool:
    return _client is not None


async def ping() -> bool:
    """Used by the health check. Returns False instead of raising on any failure.

    Creates the client if needed: on a serverless cold start the health
    check may be the very first request, before any lifespan ran.
    """
    try:
        await _ensure_client().admin.command("ping")
        return True
    except PyMongoError as exc:
        # Log the exception class only: some driver errors echo the host list.
        logger.error("mongodb_ping_failed error=%s", type(exc).__name__)
        return False
