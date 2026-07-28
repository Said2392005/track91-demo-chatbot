"""Trip repository — backs GET_TRIP_HISTORY and GET_TRIP_SUMMARY."""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class TripRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def find_trips(
        self,
        company_id: ObjectId,
        date_range: tuple[datetime, datetime],
        vehicle_id: ObjectId | None = None,
        driver_id: ObjectId | None = None,
        limit: int = 50,
    ) -> list[dict]:
        start, end = date_range
        query: dict = {"company_id": company_id, "start_time": {"$gte": start, "$lt": end}}
        if vehicle_id is not None:
            query["vehicle_id"] = vehicle_id
        if driver_id is not None:
            query["driver_id"] = driver_id
        cursor = self._db.trips.find(query).sort("start_time", 1).limit(limit)
        return await cursor.to_list(length=limit)

    async def summarize_trips(
        self,
        company_id: ObjectId,
        date_range: tuple[datetime, datetime],
        vehicle_id: ObjectId | None = None,
        vehicle_ids: list[ObjectId] | None = None,
    ) -> dict:
        start, end = date_range
        match: dict = {"company_id": company_id, "start_time": {"$gte": start, "$lt": end}}
        if vehicle_id is not None:
            match["vehicle_id"] = vehicle_id
        elif vehicle_ids is not None:
            match["vehicle_id"] = {"$in": vehicle_ids}

        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": None,
                    "trip_count": {"$sum": 1},
                    "total_distance_km": {"$sum": "$distance_km"},
                }
            },
        ]
        results = await self._db.trips.aggregate(pipeline).to_list(length=1)
        if not results:
            return {"trip_count": 0, "total_distance_km": 0.0}
        return {"trip_count": results[0]["trip_count"], "total_distance_km": results[0]["total_distance_km"]}
