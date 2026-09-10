"""Prompt configuration repository — `prompt_configurations` (new in this schema):
product-scoped, swappable system-prompt + model settings. Nothing in the DBML states "exactly
one active config per product" as a hard constraint, so `get_active` returns the first match
rather than assuming uniqueness — enforcing single-active, if wanted, is a product decision
left to the caller/service layer, not asserted here or in indexes.py."""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class PromptConfigurationRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def get_active(self, product_id: ObjectId) -> dict | None:
        return await self._db.prompt_configurations.find_one({"product_id": product_id, "is_active": True})

    async def list_by_product(self, product_id: ObjectId, limit: int = 100) -> list[dict]:
        cursor = self._db.prompt_configurations.find({"product_id": product_id}).limit(limit)
        return await cursor.to_list(length=limit)

    async def create(self, product_id: ObjectId, doc: dict, now: datetime) -> dict:
        doc = {**doc, "product_id": product_id, "created_at": now, "updated_at": now}
        result = await self._db.prompt_configurations.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc
