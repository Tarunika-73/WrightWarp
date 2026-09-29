import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.api.router import api_router
from app.core.config import get_settings
from app.db.indexes import ensure_indexes
from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database
from app.repositories.source_repository import SourceRepository

settings = get_settings()

# INFO-level structured logs (app.collection.*: collection started/completed/
# failed/blocked, with source/route/lead-time/duration/record counts - never
# secrets) would otherwise be silently dropped by Python's default WARNING
# root log level.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    await ensure_indexes(get_database())
    await SourceRepository(get_database()).sync_registry()
    yield
    await close_mongo_connection()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(health.router)
app.include_router(api_router, prefix=settings.api_v1_prefix)
