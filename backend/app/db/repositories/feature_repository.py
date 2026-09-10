"""Feature repository — `features` are product capabilities, optionally grouped by category."""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class FeatureRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def get_by_id(self, product_id: ObjectId, feature_id: ObjectId) -> dict | None:
        return await self._db.features.find_one({"product_id": product_id, "_id": feature_id})

    async def list_by_product(
        self, product_id: ObjectId, category_id: ObjectId | None = None, limit: int = 100
    ) -> list[dict]:
        query: dict = {"product_id": product_id}
        if category_id is not None:
            query["category_id"] = category_id
        cursor = self._db.features.find(query).sort("title", 1).limit(limit)
        return await cursor.to_list(length=limit)

    async def create(self, product_id: ObjectId, doc: dict, now: datetime) -> dict:
        doc = {**doc, "product_id": product_id, "created_at": now, "updated_at": now}
        result = await self._db.features.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc
