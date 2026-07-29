"""Contract tests for /health and /ready."""

import httpx
from motor.motor_asyncio import AsyncIOMotorClient


async def test_health_is_always_ok():
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_when_db_reachable(api_client):
    response = await api_client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_ready_returns_503_when_db_unreachable():
    from app.api import deps
    from app.main import app

    unreachable_client = AsyncIOMotorClient(
        "mongodb://127.0.0.1:1", serverSelectionTimeoutMS=200, connectTimeoutMS=200
    )
    app.dependency_overrides[deps.get_db] = lambda: unreachable_client["irrelevant"]

    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/ready")
    finally:
        app.dependency_overrides.clear()
        unreachable_client.close()

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
