"""
Vehicle repository — ADR 001 (repository pattern) / ADR 004 (company_id required, no default).

Phase 6 needs only the lookup methods entity resolution depends on (normalized plate ->
vehicle, nickname -> vehicle). Phase 9 will extend this same class with the query methods its
tools need (e.g. listing/filtering for GET_VEHICLE_ROSTER) — this is not the final repository,
just its first real methods.
"""

import re

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class VehicleRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def find_by_plate_number(self, company_id: ObjectId, plate_number: str) -> dict | None:
        return await self._db.vehicles.find_one({"company_id": company_id, "plate_number": plate_number})

    async def find_by_nickname(self, company_id: ObjectId, nickname: str) -> dict | None:
        return await self._db.vehicles.find_one(
            {
                "company_id": company_id,
                "nickname": {"$regex": f"^{re.escape(nickname)}$", "$options": "i"},
            }
        )

    async def get_by_id(self, company_id: ObjectId, vehicle_id: ObjectId) -> dict | None:
        return await self._db.vehicles.find_one({"company_id": company_id, "_id": vehicle_id})

    async def find_by_nickname_containing(self, company_id: ObjectId, text: str) -> dict | None:
        """Fleet-scale scan (fine at pilot scale, <50 concurrent users, small fleets per
        company): does any vehicle's nickname appear as a substring of the utterance?"""
        text_lower = text.lower()
        async for vehicle in self._db.vehicles.find({"company_id": company_id}):
            nickname = vehicle.get("nickname")
            if nickname and nickname.lower() in text_lower:
                return vehicle
        return None

    async def list_fleet_groups(self, company_id: ObjectId) -> list[str]:
        return [g for g in await self._db.vehicles.distinct("fleet_group", {"company_id": company_id}) if g]

    async def list_by_company(
        self, company_id: ObjectId, fleet_group: str | None = None, limit: int = 100
    ) -> list[dict]:
        query: dict = {"company_id": company_id}
        if fleet_group is not None:
            query["fleet_group"] = fleet_group
        cursor = self._db.vehicles.find(query).sort("plate_number", 1).limit(limit)
        return await cursor.to_list(length=limit)

    async def list_ids_by_fleet_group(self, company_id: ObjectId, fleet_group: str) -> list[ObjectId]:
        vehicles = await self.list_by_company(company_id, fleet_group=fleet_group)
        return [v["_id"] for v in vehicles]
