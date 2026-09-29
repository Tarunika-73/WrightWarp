from pymongo.asynchronous.database import AsyncDatabase

from app.db.object_id import to_str_id
from app.models.collection_error import CollectionErrorDocument

COLLECTION_NAME = "collection_errors"


class CollectionErrorRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.collection = db[COLLECTION_NAME]

    async def create(self, document: CollectionErrorDocument) -> str:
        result = await self.collection.insert_one(document.model_dump(exclude={"id"}))
        return to_str_id(result.inserted_id)

    async def find_by_search_run(self, search_run_id: str) -> list[dict]:
        docs = [doc async for doc in self.collection.find({"search_run_id": search_run_id})]
        for doc in docs:
            doc["_id"] = to_str_id(doc["_id"])
        return docs

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("search_run_id")
