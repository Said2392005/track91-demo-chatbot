from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings


@lru_cache
def get_client() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(settings.mongo_uri)


def get_database(db_name: str | None = None) -> AsyncIOMotorDatabase:
    return get_client()[db_name or settings.mongo_db_name]
