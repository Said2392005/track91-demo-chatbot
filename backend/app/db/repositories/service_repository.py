"""Service repository — `services` mirror `features`' shape (product-scoped, optionally
category-grouped) but model offerings rather than capabilities."""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class ServiceRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def get_by_id(self, product_id: ObjectId, service_id: ObjectId) -> dict | None:
        return await self._db.services.find_one({"product_id": product_id, "_id": service_id})

    async def list_by_product(
        self, product_id: ObjectId, category_id: ObjectId | None = None, limit: int = 100
    ) -> list[dict]:
        query: dict = {"product_id": product_id}
        if category_id is not None:
            query["category_id"] = category_id
        cursor = self._db.services.find(query).sort("title", 1).limit(limit)
        return await cursor.to_list(length=limit)

    async def create(self, product_id: ObjectId, doc: dict, now: datetime) -> dict:
        doc = {**doc, "product_id": product_id, "created_at": now, "updated_at": now}
        result = await self._db.services.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc
