from pymongo.asynchronous.database import AsyncDatabase

from app.db.object_id import to_str_id
from app.models.route import RouteDocument
from app.schemas.route import RouteCreate

COLLECTION_NAME = "routes"


class RouteRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.collection = db[COLLECTION_NAME]

    async def create(self, route: RouteCreate) -> str:
        document = RouteDocument(**route.model_dump())
        result = await self.collection.insert_one(document.model_dump(exclude={"id"}))
        return to_str_id(result.inserted_id)

    async def get_by_route_code(self, route_code: str) -> dict | None:
        return await self.collection.find_one({"route_code": route_code})

    async def list_active(self) -> list[dict]:
        return [doc async for doc in self.collection.find({"active": True})]

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("route_code", unique=True)
        await self.collection.create_index([("origin", 1), ("destination", 1)])
