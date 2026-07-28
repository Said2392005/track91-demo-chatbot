"""Geofence repository — see vehicle_repository.py for the pattern this follows."""

import re

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class GeofenceRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def find_by_name(self, company_id: ObjectId, name: str) -> dict | None:
        return await self._db.geofences.find_one(
            {
                "company_id": company_id,
                "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"},
            }
        )
