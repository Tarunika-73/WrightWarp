import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api import health
from app.api.router import api_router
from app.core.config import REPO_ROOT, get_settings
from app.core.errors import install_error_handlers
from app.db.indexes import ensure_indexes
from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database
from app.repositories.airport_repository import AirportRepository
from app.repositories.route_repository import RouteRepository
from app.repositories.source_repository import SourceRepository

settings = get_settings()

# INFO-level structured logs (app.collection.*: collection started/completed/
# failed/blocked, with source/route/lead-time/duration/record counts - never
# secrets) would otherwise be silently dropped by Python's default WARNING
# root log level.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("app.main")


async def bootstrap_database() -> None:
    """Idempotent: indexes + registry/master-data mirrors. Safe on every start."""
    db = get_database()
    await ensure_indexes(db)
    await SourceRepository(db).sync_registry()
    await RouteRepository(db).sync_master()
    await AirportRepository(db).sync_master()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await connect_to_mongo()
        await bootstrap_database()
    except Exception as exc:  # noqa: BLE001
        # Stay up: /health must keep answering, /health/db reports the
        # problem, and data endpoints return a 503 DATABASE_ERROR. Only the
        # exception class is logged - driver messages can echo host names.
        logger.error("startup_database_bootstrap_failed error=%s", type(exc).__name__)
    yield
    await close_mongo_connection()


DESCRIPTION = """
Real-time Airfare Price Index for India (SIH 2026 problem statement 26056, MoSPI / DIID).

**Data notice:** while no real airline/OTA source is cleared for collection, all fares
are produced by a *simulated* market and every index and backtest is labelled **DEMO**.
Route weights are DEMO values, not DGCA data.
"""

app = FastAPI(
    title="WrightWarp Airfare Price Index API",
    description=DESCRIPTION,
    version="0.3.0",
    lifespan=lifespan,
    # Swagger stays available in production: the API is public and read-only
    # apart from the CRON_SECRET-protected job endpoints.
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

install_error_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health.router)
app.include_router(api_router, prefix=settings.api_v1_prefix)


# Optional: serve the built dashboard from the same process (e.g. for a
# single-container deployment or local "production" preview). On Vercel the
# dashboard is served by the CDN instead and this directory is not bundled.
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
if (FRONTEND_DIST / "index.html").is_file():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith(("api/", "health")):
            from app.core.errors import NotFoundError

            raise NotFoundError("Not Found")
        candidate = (FRONTEND_DIST / path).resolve()
        if path and candidate.is_file() and Path(FRONTEND_DIST.resolve()) in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
