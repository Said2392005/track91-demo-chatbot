"""Chat message repository — `chat_messages` (renamed from `messages` in the source DBML,
see schema_definitions.py). Shape changed to match the new schema exactly: session_id-scoped
only (no company_id — chat_messages has no tenant field of its own in the DBML, so any
org/product-scoped query has to join through chat_sessions), and it now carries
model_provider/model_name/token counts/latency_ms/status per message instead of
intent/tool_called. The old llm_usage collection's per-call-type usage tracking has no home
here — see schema_definitions.py's module docstring and the standalone gap report."""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class ChatMessageRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def insert(
        self,
        session_id: ObjectId,
        role: str,
        content: str,
        now: datetime,
        model_provider: str | None = None,
        model_name: str | None = None,
        prompt_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        latency_ms: int | None = None,
        status: str | None = None,
    ) -> None:
        doc = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": now,
        }
        for key, value in (
            ("model_provider", model_provider),
            ("model_name", model_name),
            ("prompt_tokens", prompt_tokens),
            ("output_tokens", output_tokens),
            ("total_tokens", total_tokens),
            ("latency_ms", latency_ms),
            ("status", status),
        ):
            if value is not None:
                doc[key] = value
        await self._db.chat_messages.insert_one(doc)

    async def list_for_session(self, session_id: ObjectId, limit: int = 100) -> list[dict]:
        cursor = self._db.chat_messages.find({"session_id": session_id}).sort("created_at", 1).limit(limit)
        return await cursor.to_list(length=limit)
