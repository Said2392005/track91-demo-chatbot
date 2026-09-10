"""Document repository — `documents` (product-scoped) replaces the old `documents_meta`
collection. Field shape changed: `source_type` is now a free string (no DOCUMENT_SOURCE_TYPES
enum — see schema_definitions.py's module docstring) and there is no `approved_pricing` /
`is_active` gating, since the pricing-intent gate those flags served was fleet-domain-specific
business logic with no stated analog here."""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class DocumentRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def get_by_id(self, product_id: ObjectId, document_id: ObjectId) -> dict | None:
        return await self._db.documents.find_one({"product_id": product_id, "_id": document_id})

    async def list_by_product(self, product_id: ObjectId, limit: int = 100) -> list[dict]:
        cursor = self._db.documents.find({"product_id": product_id}).limit(limit)
        return await cursor.to_list(length=limit)

    async def create(self, product_id: ObjectId, doc: dict, now: datetime) -> dict:
        doc = {**doc, "product_id": product_id, "created_at": now, "updated_at": now}
        result = await self._db.documents.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc
