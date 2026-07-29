"""Chat message repository — backs POST /chat's transcript persistence and
GET /chat/{session_id}/history."""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class ChatMessageRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def insert(
        self,
        company_id: ObjectId,
        session_id: ObjectId,
        role: str,
        content: str,
        now: datetime,
        intent: str | None = None,
        tool_called: str | None = None,
    ) -> None:
        doc = {
            "session_id": session_id,
            "company_id": company_id,
            "role": role,
            "content": content,
            "created_at": now,
        }
        if intent is not None:
            doc["intent"] = intent
        if tool_called is not None:
            doc["tool_called"] = tool_called
        await self._db.chat_messages.insert_one(doc)

    async def list_for_session(self, company_id: ObjectId, session_id: ObjectId, limit: int = 100) -> list[dict]:
        cursor = self._db.chat_messages.find({"company_id": company_id, "session_id": session_id}).sort(
            "created_at", 1
        ).limit(limit)
        return await cursor.to_list(length=limit)
