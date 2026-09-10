"""Knowledge item repository — `knowledge_items` (new in this schema): product-scoped
structured knowledge-base entries, distinct from `documents`/`document_chunks` (unstructured,
chunked/embedded content for RAG)."""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class KnowledgeItemRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def get_by_id(self, product_id: ObjectId, item_id: ObjectId) -> dict | None:
        return await self._db.knowledge_items.find_one({"product_id": product_id, "_id": item_id})

    async def list_by_product(
        self, product_id: ObjectId, content_type: str | None = None, limit: int = 100
    ) -> list[dict]:
        query: dict = {"product_id": product_id}
        if content_type is not None:
            query["content_type"] = content_type
        cursor = self._db.knowledge_items.find(query).limit(limit)
        return await cursor.to_list(length=limit)

    async def create(self, product_id: ObjectId, doc: dict, now: datetime) -> dict:
        doc = {**doc, "product_id": product_id, "created_at": now, "updated_at": now}
        result = await self._db.knowledge_items.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc
