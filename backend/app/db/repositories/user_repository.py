"""
User repository. `find_by_email` remains the one deliberate exception to requiring a scoping
id up front: at login time we don't know the caller's org_id yet — that's what this lookup is
for. `email` is globally unique (users.email_unique index in indexes.py), so this is safe
without an org_id filter. Every other method here requires org_id.

`company_id` renamed to `org_id` throughout to match the new `organizations` collection.
"""

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class UserRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def find_by_email(self, email: str) -> dict | None:
        return await self._db.users.find_one({"email": email})

    async def get_by_id(self, org_id: ObjectId, user_id: ObjectId) -> dict | None:
        return await self._db.users.find_one({"org_id": org_id, "_id": user_id})
