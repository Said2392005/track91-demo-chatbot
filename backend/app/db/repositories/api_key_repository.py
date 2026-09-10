"""API key repository — `api_keys` are org-scoped, optionally product-scoped credentials.
Only `key_hash` is ever stored/queried — the plaintext key is never persisted."""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class ApiKeyRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def find_by_key_hash(self, key_hash: str) -> dict | None:
        return await self._db.api_keys.find_one({"key_hash": key_hash})

    async def list_by_org(self, org_id: ObjectId, limit: int = 100) -> list[dict]:
        cursor = self._db.api_keys.find({"org_id": org_id}).limit(limit)
        return await cursor.to_list(length=limit)

    async def create(self, org_id: ObjectId, doc: dict, now: datetime) -> dict:
        doc = {**doc, "org_id": org_id, "created_at": now, "updated_at": now}
        result = await self._db.api_keys.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    async def touch_last_used(self, key_id: ObjectId, now: datetime) -> None:
        await self._db.api_keys.update_one({"_id": key_id}, {"$set": {"last_used_at": now}})
