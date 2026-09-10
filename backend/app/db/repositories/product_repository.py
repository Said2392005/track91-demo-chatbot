"""Product repository — `products` is the new schema's org-scoped content container
(replaces the fleet domain's role as the thing chat sessions/documents/knowledge hang off of)."""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class ProductRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def get_by_id(self, org_id: ObjectId, product_id: ObjectId) -> dict | None:
        return await self._db.products.find_one({"org_id": org_id, "_id": product_id})

    async def list_by_org(self, org_id: ObjectId, limit: int = 100) -> list[dict]:
        cursor = self._db.products.find({"org_id": org_id}).sort("title", 1).limit(limit)
        return await cursor.to_list(length=limit)

    async def create(self, org_id: ObjectId, doc: dict, now: datetime) -> dict:
        doc = {**doc, "org_id": org_id, "created_at": now, "updated_at": now}
        result = await self._db.products.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc
