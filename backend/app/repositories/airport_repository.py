from pymongo.asynchronous.database import AsyncDatabase

from app.core.routes import AIRPORTS

from app.db.object_id import to_str_id
from app.models.airport import AirportDocument

COLLECTION_NAME = "airports"


class AirportRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.collection = db[COLLECTION_NAME]

    async def create(self, airport: AirportDocument) -> str:
        result = await self.collection.insert_one(airport.model_dump(exclude={"id"}))
        return to_str_id(result.inserted_id)

    async def get_by_iata_code(self, iata_code: str) -> dict | None:
        return await self.collection.find_one({"iata_code": iata_code})

    async def sync_master(self) -> None:
        for airport in AIRPORTS:
            await self.collection.update_one(
                {"iata_code": airport.iata_code},
                {"$set": {"name": airport.name, "city": airport.city, "state": airport.state, "active": True}},
                upsert=True,
            )

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("iata_code", unique=True)
