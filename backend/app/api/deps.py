import hmac

from fastapi import Header, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings
from app.core.errors import ServiceMisconfiguredError, UnauthorizedError
from app.db.mongodb import get_database


def get_db() -> AsyncDatabase:
    """FastAPI dependency yielding the application's MongoDB database handle.

    Named ``get_db`` (not ``get_database``) to keep the dependency-override
    pattern used by tests (``app.dependency_overrides[get_db] = ...``)
    stable across the PostgreSQL -> MongoDB migration.
    """
    return get_database()


def require_cron_secret(authorization: str | None = Header(default=None)) -> None:
    """Guards scheduled/administrative endpoints with ``Authorization: Bearer <CRON_SECRET>``.

    Vercel Cron sends exactly this header when ``CRON_SECRET`` is set on the
    project. With no secret configured the endpoint refuses everything - it
    never runs unprotected.
    """
    secret = get_settings().cron_secret
    if not secret:
        raise ServiceMisconfiguredError("CRON_SECRET is not configured; scheduled endpoints are disabled")
    expected = f"Bearer {secret}"
    if not authorization or not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise UnauthorizedError("Missing or invalid bearer token")


class Pagination:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="1-based page number"),
        page_size: int = Query(50, ge=1, le=500, description="Items per page (max 500)"),
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.page_size


__all__ = ["get_db", "require_cron_secret", "Pagination"]
