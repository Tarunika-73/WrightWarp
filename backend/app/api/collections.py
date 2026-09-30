"""Development endpoints for exercising the collection framework.

Deliberately NOT a generic scraping endpoint: the client selects a
registered ``source_id`` (app.core.sources) and the corresponding
adapter, looked up server-side, controls what is actually accessed. There
is no way to pass an arbitrary URL through this API.
"""
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import Pagination, get_db
from app.core.enums import SearchRunStatus
from app.collection.service import CollectionService
from app.db.bson_utils import datetime_to_date
from app.repositories.search_run_repository import SearchRunRepository
from app.schemas.collection import CollectionRequest, CollectionResult, SearchRunOut

router = APIRouter(prefix="/collections", tags=["collections"])


@router.post("", response_model=CollectionResult)
async def create_collection(request: CollectionRequest, db: AsyncDatabase = Depends(get_db)) -> CollectionResult:
    service = CollectionService(db)
    return await service.run(request)


@router.get("", summary="Recent collection runs (checkpoints), newest first")
async def list_collections(
    source: str | None = Query(None),
    status: SearchRunStatus | None = Query(None),
    route: str | None = Query(None, description="e.g. DEL-BOM"),
    pagination: Pagination = Depends(),
    db: AsyncDatabase = Depends(get_db),
) -> dict:
    query: dict = {}
    if source:
        query["source"] = source
    if status:
        query["status"] = status.value
    if route:
        query["route"] = route.upper()
    collection = db["search_runs"]
    total = await collection.count_documents(query)
    cursor = collection.find(query).sort([("started_at", -1)]).skip(pagination.skip).limit(pagination.page_size)
    items = []
    async for run in cursor:
        run["id"] = str(run.pop("_id"))
        if run.get("travel_date") is not None:
            run["travel_date"] = datetime_to_date(run["travel_date"])
        items.append(SearchRunOut.model_validate(run))
    return {
        "items": items,
        "page": {"page": pagination.page, "page_size": pagination.page_size, "total": total, "pages": math.ceil(total / pagination.page_size) if total else 0},
    }


@router.get("/{collection_id}", response_model=SearchRunOut)
async def get_collection(collection_id: str, db: AsyncDatabase = Depends(get_db)) -> dict:
    try:
        run = await SearchRunRepository(db).get_by_id(collection_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Collection not found")
    if run is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    run["id"] = run.pop("_id")
    if run.get("travel_date") is not None:
        run["travel_date"] = datetime_to_date(run["travel_date"])
    return run
