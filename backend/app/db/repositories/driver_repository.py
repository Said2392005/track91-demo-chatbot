"""Driver repository — see vehicle_repository.py for the pattern this follows."""

import re

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class DriverRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def find_by_name(self, company_id: ObjectId, name: str) -> list[dict]:
        """Case-insensitive exact-name match. Returns a list (not a single doc) so the caller
        can detect name collisions within a company and route to CLARIFICATION_NEEDED rather
        than silently picking one, per entity-taxonomy.md."""
        cursor = self._db.drivers.find(
            {
                "company_id": company_id,
                "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"},
            }
        )
        return await cursor.to_list(length=10)

    async def get_by_id(self, company_id: ObjectId, driver_id: ObjectId) -> dict | None:
        return await self._db.drivers.find_one({"company_id": company_id, "_id": driver_id})
