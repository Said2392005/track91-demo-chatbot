import os
import uuid

import httpx
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.db.init_db import init_db

TEST_MONGO_URI = os.environ.get("TEST_MONGO_URI", "mongodb://127.0.0.1:27017")

# Tests never depend on jwt_secret_key being unset — set once so PyJWT has a real HMAC key
# rather than an empty-string default.
settings.jwt_secret_key = settings.jwt_secret_key or "test-only-jwt-secret-not-for-production"


@pytest_asyncio.fixture(scope="session")
async def db():
    """A real MongoDB database (not a fake) — schema validators and index creation are
    genuine MongoDB server behavior that in-memory fakes don't faithfully reproduce."""
    client = AsyncIOMotorClient(TEST_MONGO_URI, tz_aware=True)  # match app/db/client.py
    db_name = f"test_fleet_chatbot_{uuid.uuid4().hex[:8]}"
    database = client[db_name]
    await init_db(database)
    yield database
    await client.drop_database(db_name)
    client.close()


class _DefaultFakeGraph:
    """Harmless placeholder so routes that resolve get_graph via FastAPI's dependency chain
    (every /chat* route, even ones — like a malformed-session-id 400 or a not-found 404 —
    whose handler body never actually calls the graph) don't blow up on `request.app.state.graph`
    being unset (lifespan never runs under ASGITransport). Tests that care what the graph
    returns override `deps.get_graph` again themselves, which simply replaces this entry."""

    async def ainvoke(self, input_state: dict, config: dict | None = None) -> dict:
        return {**input_state, "response_text": "", "final_intent": None, "citations": []}


@pytest_asyncio.fixture
async def api_client(db):
    """An httpx client bound to the real FastAPI app via ASGITransport (no real server, no
    lifespan triggered — verified empirically: plain ASGITransport doesn't invoke FastAPI's
    lifespan, so this never touches real Chroma/checkpointer/LLM infra), with `get_db`
    pre-overridden to the isolated test database and `get_graph` pre-overridden to a harmless
    default. Tests needing specific graph behavior override `deps.get_graph` themselves on top
    of this."""
    from app.api import deps
    from app.main import app

    app.dependency_overrides[deps.get_db] = lambda: db
    app.dependency_overrides[deps.get_graph] = lambda: _DefaultFakeGraph()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
