"""
Session repository — ADR 001 (repository pattern) / ADR 004 (company_id required, no default).

Owns `chat_sessions`: our own business-level session/active-entity data. Deliberately separate
from LangGraph's own checkpoint collections (app/memory/checkpointer.py) — those store raw
graph/message state keyed by thread_id via LangGraph's own serialization protocol, while
`active_entities` is domain data (which vehicle/driver/geofence is "active" for coreference,
Phase 6) that app/memory/active_entity_tracker.py reads directly as a plain dict.
"""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class SessionRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def create(self, company_id: ObjectId, user_id: ObjectId, now: datetime) -> dict:
        doc = {
            "company_id": company_id,
            "user_id": user_id,
            "status": "active",
            "started_at": now,
            "last_active_at": now,
        }
        result = await self._db.chat_sessions.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    async def get(self, company_id: ObjectId, session_id: ObjectId) -> dict | None:
        return await self._db.chat_sessions.find_one({"company_id": company_id, "_id": session_id})

    async def touch(self, company_id: ObjectId, session_id: ObjectId, now: datetime) -> None:
        """Bumps last_active_at — the field the session-level TTL index (indexes.py) uses to
        implement a sliding idle-timeout. Call on every turn."""
        await self._db.chat_sessions.update_one(
            {"company_id": company_id, "_id": session_id}, {"$set": {"last_active_at": now}}
        )

    async def get_active_entities(self, company_id: ObjectId, session_id: ObjectId) -> tuple[dict, datetime | None]:
        doc = await self.get(company_id, session_id)
        if doc is None:
            return {}, None
        return doc.get("active_entities", {}), doc.get("active_entities_updated_at")

    async def set_active_entity(
        self,
        company_id: ObjectId,
        session_id: ObjectId,
        entity_type: str,
        entity_id: ObjectId,
        now: datetime,
    ) -> None:
        """Last-reference-wins: setting a new active vehicle replaces the previous one for that
        type, rather than stacking a history — resolves the open question in
        docs/phase-1-planning/entity-taxonomy.md's Phase 8 notes."""
        await self._db.chat_sessions.update_one(
            {"company_id": company_id, "_id": session_id},
            {
                "$set": {
                    f"active_entities.{entity_type}_id": entity_id,
                    "active_entities_updated_at": now,
                    "last_active_at": now,
                }
            },
        )
