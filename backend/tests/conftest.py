import os
import uuid

import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from app.db.init_db import init_db

TEST_MONGO_URI = os.environ.get("TEST_MONGO_URI", "mongodb://127.0.0.1:27017")


@pytest_asyncio.fixture(scope="session")
async def db():
    """A real MongoDB database (not a fake) — schema validators and index creation are
    genuine MongoDB server behavior that in-memory fakes don't faithfully reproduce."""
    client = AsyncIOMotorClient(TEST_MONGO_URI)
    db_name = f"test_fleet_chatbot_{uuid.uuid4().hex[:8]}"
    database = client[db_name]
    await init_db(database)
    yield database
    await client.drop_database(db_name)
    client.close()
