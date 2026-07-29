"""
User repository. `find_by_email` is the one deliberate, documented exception to ADR 004's
"every method requires company_id" rule in this codebase: at login time we don't know the
caller's company_id yet — that's precisely what looking the user up is for. `email` is globally
unique (Phase 3's `users.email_unique` index, not company-scoped), so this lookup is safe and
well-defined without a company_id filter. Every other method here — and every method on every
other repository — still requires it.
"""

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class UserRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def find_by_email(self, email: str) -> dict | None:
        return await self._db.users.find_one({"email": email})

    async def get_by_id(self, company_id: ObjectId, user_id: ObjectId) -> dict | None:
        return await self._db.users.find_one({"company_id": company_id, "_id": user_id})
