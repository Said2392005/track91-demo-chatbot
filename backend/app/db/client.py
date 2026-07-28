from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings


@lru_cache
def get_client() -> AsyncIOMotorClient:
    # tz_aware=True: without it, pymongo/motor read datetimes back as naive (even though we
    # always write timezone-aware UTC values) — confirmed to raise TypeError on any later
    # `datetime.now(timezone.utc) - value_read_from_mongo` arithmetic, which Phase 8's
    # active-entity TTL check is the first place in this codebase to actually do.
    return AsyncIOMotorClient(settings.mongo_uri, tz_aware=True)


def get_database(db_name: str | None = None) -> AsyncIOMotorDatabase:
    return get_client()[db_name or settings.mongo_db_name]
