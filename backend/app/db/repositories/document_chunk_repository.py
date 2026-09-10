"""Document chunk repository — `document_chunks` (unchanged in shape/purpose from the old
schema: still document_id + product_id scoped, still just a pointer at `vector_id` into the
external vector store)."""

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class DocumentChunkRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def list_for_document(self, document_id: ObjectId, limit: int = 500) -> list[dict]:
        cursor = self._db.document_chunks.find({"document_id": document_id}).sort("chunk_index", 1).limit(limit)
        return await cursor.to_list(length=limit)

    async def insert_many(self, chunks: list[dict]) -> list[ObjectId]:
        result = await self._db.document_chunks.insert_many(chunks)
        return list(result.inserted_ids)
