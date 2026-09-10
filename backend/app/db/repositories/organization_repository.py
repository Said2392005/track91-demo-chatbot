"""Organization repository — root tenant entity in the new schema (was `companies`)."""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class OrganizationRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def get_by_id(self, org_id: ObjectId) -> dict | None:
        return await self._db.organizations.find_one({"_id": org_id})

    async def find_by_organization_code(self, organization_code: str) -> dict | None:
        return await self._db.organizations.find_one({"organization_code": organization_code})

    async def create(self, doc: dict, now: datetime) -> dict:
        doc = {**doc, "created_at": now, "updated_at": now}
        result = await self._db.organizations.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc
