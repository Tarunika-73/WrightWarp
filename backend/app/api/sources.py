"""Development endpoint for inspecting the source registry.

Reads from the ``sources`` collection (kept in sync with
``app.core.sources.ALL_SOURCES`` at startup - see
``app.repositories.source_repository``), not the Python module directly,
so this goes through the same repository pattern as every other
collection. There is still no way to create, enable, or otherwise change
a source through this API - compliance status is a code-level decision.
"""
from fastapi import APIRouter, Depends
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_db
from app.repositories.source_repository import SourceRepository
from app.schemas.source import SourceOut

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[SourceOut])
async def get_sources(db: AsyncDatabase = Depends(get_db)) -> list[SourceOut]:
    documents = await SourceRepository(db).list_all()
    return [SourceOut.model_validate(doc) for doc in documents]
