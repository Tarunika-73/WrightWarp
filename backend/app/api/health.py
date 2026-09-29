from fastapi import APIRouter

from app.core.config import get_settings
from app.db.mongodb import ping
from app.schemas.health import DatabaseHealthResponse, HealthResponse

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check - FastAPI is up. Deliberately does not depend on MongoDB
    being reachable, so this endpoint stays fast and reliable even if the
    database is degraded; see ``/health/db`` for that."""
    return HealthResponse(status="ok", service=settings.app_name)


@router.get("/health/db", response_model=DatabaseHealthResponse)
async def health_db() -> DatabaseHealthResponse:
    reachable = await ping()
    return DatabaseHealthResponse(
        status="ok" if reachable else "error",
        service=settings.app_name,
        database="mongodb" if reachable else "error: MongoDB unreachable",
    )
