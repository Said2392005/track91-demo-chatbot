"""
Session repository — owns `chat_sessions`, now scoped by `product_id` (was `company_id`),
matching the new schema's chat_sessions(product_id, prompt_id, user_id, session_key, ip_hash,
status, started_at, ended_at, last_active_at).

BREAKING CHANGE, left unresolved here: the old chat_sessions also carried `active_entities`
(which vehicle/driver/geofence is "active" for coreference) and `pending_clarification`
(cross-turn clarification state) — both fleet-domain NLU/coreference concepts with no field in
the new schema and no defined replacement. Their accessor methods (get_active_entities,
set_active_entity, set_pending_clarification, pop_pending_clarification) are removed here, not
reimplemented against something that doesn't exist. Callers — app/router/router.py,
app/router/clarification.py, app/nlu/coreference.py, app/memory/active_entity_tracker.py,
app/agent/nodes.py — still call the old methods and will break until the NLU/agent layer's
replacement design is decided (see the standalone report on that gap).
"""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class SessionRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def create(self, product_id: ObjectId, user_id: ObjectId | None, now: datetime) -> dict:
        doc = {
            "product_id": product_id,
            "user_id": user_id,
            "status": "active",
            "started_at": now,
            "last_active_at": now,
        }
        result = await self._db.chat_sessions.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    async def get(self, product_id: ObjectId, session_id: ObjectId) -> dict | None:
        return await self._db.chat_sessions.find_one({"product_id": product_id, "_id": session_id})

    async def get_by_session_key(self, session_key: str) -> dict | None:
        return await self._db.chat_sessions.find_one({"session_key": session_key})

    async def touch(self, product_id: ObjectId, session_id: ObjectId, now: datetime) -> None:
        await self._db.chat_sessions.update_one(
            {"product_id": product_id, "_id": session_id}, {"$set": {"last_active_at": now}}
        )

    async def close(self, product_id: ObjectId, session_id: ObjectId, now: datetime) -> None:
        await self._db.chat_sessions.update_one(
            {"product_id": product_id, "_id": session_id},
            {"$set": {"status": "closed", "ended_at": now, "last_active_at": now}},
        )
