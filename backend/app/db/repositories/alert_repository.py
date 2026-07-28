"""Alert repository — backs GET_ALERT_HISTORY and the driver-behavior aggregation used by
GET_DRIVER_BEHAVIOR_REPORT."""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class AlertRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def find_alerts(
        self,
        company_id: ObjectId,
        date_range: tuple[datetime, datetime],
        vehicle_id: ObjectId | None = None,
        driver_id: ObjectId | None = None,
        alert_type: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        start, end = date_range
        query: dict = {"company_id": company_id, "triggered_at": {"$gte": start, "$lt": end}}
        if vehicle_id is not None:
            query["vehicle_id"] = vehicle_id
        if driver_id is not None:
            query["driver_id"] = driver_id
        if alert_type is not None:
            query["alert_type"] = alert_type
        cursor = self._db.alerts.find(query).sort("triggered_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def count_alerts_by_type(
        self, company_id: ObjectId, driver_id: ObjectId, date_range: tuple[datetime, datetime]
    ) -> dict[str, int]:
        start, end = date_range
        pipeline = [
            {
                "$match": {
                    "company_id": company_id,
                    "driver_id": driver_id,
                    "triggered_at": {"$gte": start, "$lt": end},
                }
            },
            {"$group": {"_id": "$alert_type", "count": {"$sum": 1}}},
        ]
        results = await self._db.alerts.aggregate(pipeline).to_list(length=None)
        return {r["_id"]: r["count"] for r in results}
