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

    async def list_for_vehicle_or_group(
        self,
        company_id: ObjectId,
        vehicle_id: ObjectId | None = None,
        fleet_group: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        query: dict = {"company_id": company_id, "active": True}
        if vehicle_id is not None and fleet_group is not None:
            query["$or"] = [{"vehicle_ids": vehicle_id}, {"fleet_group": fleet_group}]
        elif vehicle_id is not None:
            query["vehicle_ids"] = vehicle_id
        elif fleet_group is not None:
            query["fleet_group"] = fleet_group
        cursor = self._db.geofences.find(query).sort("name", 1).limit(limit)
        return await cursor.to_list(length=limit)
