from pymongo.asynchronous.database import AsyncDatabase

from app.db.object_id import to_str_id
from app.models.airline import AirlineDocument

COLLECTION_NAME = "airlines"


class AirlineRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.collection = db[COLLECTION_NAME]

    async def create(self, airline: AirlineDocument) -> str:
        result = await self.collection.insert_one(airline.model_dump(exclude={"id"}))
        return to_str_id(result.inserted_id)

    async def get_by_code(self, code: str) -> dict | None:
        return await self.collection.find_one({"code": code})

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("code", unique=True)
