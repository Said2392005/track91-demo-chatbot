"""Maintenance repository — backs GET_MAINTENANCE_HISTORY and GET_MAINTENANCE_DUE."""

from datetime import datetime, timedelta

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

DUE_SOON_WINDOW = timedelta(days=14)


class MaintenanceRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def find_history(
        self,
        company_id: ObjectId,
        vehicle_id: ObjectId,
        date_range: tuple[datetime, datetime] | None = None,
        limit: int = 50,
    ) -> list[dict]:
        query: dict = {"company_id": company_id, "vehicle_id": vehicle_id}
        if date_range is not None:
            start, end = date_range
            query["service_date"] = {"$gte": start, "$lt": end}
        cursor = self._db.maintenance_records.find(query).sort("service_date", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def find_due(
        self,
        company_id: ObjectId,
        now: datetime,
        vehicle_id: ObjectId | None = None,
        vehicle_ids: list[ObjectId] | None = None,
    ) -> list[dict]:
        """"Due" = next_due_date within DUE_SOON_WINDOW from now, including already overdue."""
        query: dict = {"company_id": company_id, "next_due_date": {"$lte": now + DUE_SOON_WINDOW}}
        if vehicle_id is not None:
            query["vehicle_id"] = vehicle_id
        elif vehicle_ids is not None:
            query["vehicle_id"] = {"$in": vehicle_ids}
        cursor = self._db.maintenance_records.find(query).sort("next_due_date", 1)
        return await cursor.to_list(length=100)
