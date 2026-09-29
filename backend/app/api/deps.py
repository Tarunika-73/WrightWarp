from pymongo.asynchronous.database import AsyncDatabase

from app.db.mongodb import get_database


def get_db() -> AsyncDatabase:
    """FastAPI dependency yielding the application's MongoDB database handle.

    Named ``get_db`` (not ``get_database``) to keep the dependency-override
    pattern used by tests (``app.dependency_overrides[get_db] = ...``)
    stable across the PostgreSQL -> MongoDB migration.
    """
    return get_database()


__all__ = ["get_db"]
