"""
Idempotent schema + index setup. Safe to re-run: existing collections get their validator
updated in place (collMod) rather than re-created, and index creation is a no-op if an
identically-named index already exists.

Usage: python -m app.db.init_db
"""

import asyncio
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.client import get_database
from app.db.indexes import INDEX_DEFINITIONS
from app.db.schema_definitions import COLLECTION_VALIDATORS

logger = logging.getLogger(__name__)


async def init_collections(db: AsyncIOMotorDatabase) -> None:
    existing = set(await db.list_collection_names())

    for name, validator in COLLECTION_VALIDATORS.items():
        if name in existing:
            await db.command(
                "collMod",
                name,
                validator=validator,
                validationLevel="moderate",
                validationAction="error",
            )
            logger.info("Updated validator for existing collection: %s", name)
        else:
            await db.create_collection(
                name,
                validator=validator,
                validationLevel="moderate",
                validationAction="error",
            )
            logger.info("Created collection with validator: %s", name)


async def init_indexes(db: AsyncIOMotorDatabase) -> None:
    for name, index_specs in INDEX_DEFINITIONS.items():
        collection = db[name]
        for keys, options in index_specs:
            await collection.create_index(keys, **options)
        logger.info("Ensured %d index(es) on: %s", len(index_specs), name)


async def init_db(db: AsyncIOMotorDatabase | None = None) -> AsyncIOMotorDatabase:
    db = db if db is not None else get_database()
    await init_collections(db)
    await init_indexes(db)
    return db


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(init_db())
