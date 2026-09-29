"""Repository for the ``sources`` collection.

This is a mirror of ``app.core.sources.ALL_SOURCES`` for querying, not
an independent source of truth - see ``app.models.source.SourceDocument``
for why. ``sync_registry`` is idempotent (upsert by ``source_id``) and is
called once at FastAPI startup.
"""
from pymongo.asynchronous.database import AsyncDatabase

from app.core.sources import SourceDefinition, list_sources
from app.models.source import SourceDocument

COLLECTION_NAME = "sources"


def _to_document(definition: SourceDefinition) -> dict:
    return SourceDocument(
        source_id=definition.source_id,
        display_name=definition.display_name,
        source_type=definition.source_type,
        enabled=definition.enabled,
        status=definition.status,
        robots_url=definition.robots_url,
        terms_url=definition.terms_url,
        rate_limit_per_minute=definition.rate_limit_per_minute,
        requires_browser=definition.requires_browser,
        requires_terms_review=definition.requires_terms_review,
        requires_robots_review=definition.requires_robots_review,
        notes=definition.notes,
    ).model_dump(exclude={"id"})


class SourceRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.collection = db[COLLECTION_NAME]

    async def sync_registry(self) -> None:
        for definition in list_sources():
            await self.collection.update_one(
                {"source_id": definition.source_id},
                {"$set": _to_document(definition)},
                upsert=True,
            )

    async def list_all(self) -> list[dict]:
        return [doc async for doc in self.collection.find({}, {"_id": 0})]

    async def get_by_source_id(self, source_id: str) -> dict | None:
        return await self.collection.find_one({"source_id": source_id}, {"_id": 0})

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("source_id", unique=True)
