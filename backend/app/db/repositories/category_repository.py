"""Category repository — `categories` groups a product's `features`/`services`."""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class CategoryRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def get_by_id(self, product_id: ObjectId, category_id: ObjectId) -> dict | None:
        return await self._db.categories.find_one({"product_id": product_id, "_id": category_id})

    async def list_by_product(self, product_id: ObjectId, limit: int = 100) -> list[dict]:
        cursor = self._db.categories.find({"product_id": product_id}).sort("name", 1).limit(limit)
        return await cursor.to_list(length=limit)

    async def create(self, product_id: ObjectId, doc: dict, now: datetime) -> dict:
        doc = {**doc, "product_id": product_id, "created_at": now, "updated_at": now}
        result = await self._db.categories.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc
