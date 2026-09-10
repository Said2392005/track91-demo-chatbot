"""Auth session repository — `auth_sessions` (new in this schema) is a login/token session,
distinct from `chat_sessions` (a product chat conversation). The old schema had no separate
login-session collection; auth state lived only in issued JWTs. Whether this repository
should replace or sit alongside that JWT flow is a decision for app/services/auth_service.py,
not made here."""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class AuthSessionRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def find_by_access_token_hash(self, access_token_hash: str) -> dict | None:
        return await self._db.auth_sessions.find_one({"access_token_hash": access_token_hash})

    async def find_by_refresh_token_hash(self, refresh_token_hash: str) -> dict | None:
        return await self._db.auth_sessions.find_one({"refresh_token_hash": refresh_token_hash})

    async def create(self, user_id: ObjectId, doc: dict, now: datetime) -> dict:
        doc = {**doc, "user_id": user_id, "status": "active", "created_at": now, "updated_at": now}
        result = await self._db.auth_sessions.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    async def revoke(self, session_id: ObjectId, now: datetime) -> None:
        await self._db.auth_sessions.update_one(
            {"_id": session_id}, {"$set": {"status": "revoked", "updated_at": now}}
        )
