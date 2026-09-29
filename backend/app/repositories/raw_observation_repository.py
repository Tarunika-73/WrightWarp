from pymongo.asynchronous.database import AsyncDatabase

from app.db.object_id import to_object_id, to_str_id
from app.models.raw_observation import RawObservationDocument

COLLECTION_NAME = "raw_observations"


class RawObservationRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.collection = db[COLLECTION_NAME]

    async def create(self, document: RawObservationDocument) -> str:
        result = await self.collection.insert_one(document.model_dump(exclude={"id"}))
        return to_str_id(result.inserted_id)

    async def set_status(self, observation_id: str, status: str) -> None:
        await self.collection.update_one(
            {"_id": to_object_id(observation_id)}, {"$set": {"status": status}}
        )

    async def find_by_search_run(self, search_run_id: str) -> list[dict]:
        docs = [doc async for doc in self.collection.find({"search_run_id": search_run_id})]
        for doc in docs:
            doc["_id"] = to_str_id(doc["_id"])
        return docs

    async def count_by_search_run(self, search_run_id: str) -> int:
        return await self.collection.count_documents({"search_run_id": search_run_id})

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("search_run_id")
        await self.collection.create_index("payload_hash")
