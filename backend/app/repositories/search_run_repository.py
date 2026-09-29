from datetime import datetime

from pymongo.asynchronous.database import AsyncDatabase

from app.core.enums import SearchRunStatus
from app.db.object_id import to_object_id, to_str_id
from app.models.search_run import SearchRunDocument

COLLECTION_NAME = "search_runs"


class SearchRunRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.collection = db[COLLECTION_NAME]

    async def create(self, document: SearchRunDocument) -> str:
        result = await self.collection.insert_one(document.model_dump(exclude={"id"}))
        return to_str_id(result.inserted_id)

    async def finalize(
        self,
        search_run_id: str,
        *,
        status: SearchRunStatus,
        completed_at: datetime,
        records_found: int,
        records_valid: int,
        error_message: str | None,
    ) -> None:
        await self.collection.update_one(
            {"_id": to_object_id(search_run_id)},
            {
                "$set": {
                    "status": status.value,
                    "completed_at": completed_at,
                    "records_found": records_found,
                    "records_valid": records_valid,
                    "error_message": error_message,
                }
            },
        )

    async def get_by_id(self, search_run_id: str) -> dict | None:
        doc = await self.collection.find_one({"_id": to_object_id(search_run_id)})
        if doc is not None:
            doc["_id"] = to_str_id(doc["_id"])
        return doc

    async def ensure_indexes(self) -> None:
        await self.collection.create_index([("source", 1), ("route", 1), ("travel_date", 1), ("lead_days", 1)])
        await self.collection.create_index("status")
        await self.collection.create_index([("started_at", -1)])
