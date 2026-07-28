"""
Active-entity expiry tests — Phase 8 requirement: active_entities must expire, not persist
indefinitely. settings.active_entity_ttl_seconds defaults to 30 minutes.
"""

from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from app.core.config import settings
from app.db.repositories.session_repository import SessionRepository
from app.memory.active_entity_tracker import get_active_entities, set_active_entity


@pytest.fixture
async def session(db):
    repo = SessionRepository(db)
    company_id, user_id = ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)
    created = await repo.create(company_id, user_id, now)
    return repo, company_id, created["_id"]


async def test_fresh_active_entity_resolves(session):
    repo, company_id, session_id = session
    vehicle_id = ObjectId()
    now = datetime.now(timezone.utc)

    await set_active_entity(repo, company_id, session_id, "vehicle", vehicle_id, now)
    result = await get_active_entities(repo, company_id, session_id, now=now + timedelta(minutes=5))

    assert result["vehicle_id"] == vehicle_id


async def test_active_entity_within_ttl_still_resolves(session):
    repo, company_id, session_id = session
    vehicle_id = ObjectId()
    t0 = datetime.now(timezone.utc)

    await set_active_entity(repo, company_id, session_id, "vehicle", vehicle_id, t0)
    just_inside_ttl = t0 + timedelta(seconds=settings.active_entity_ttl_seconds - 5)

    result = await get_active_entities(repo, company_id, session_id, now=just_inside_ttl)
    assert result["vehicle_id"] == vehicle_id


async def test_active_entity_past_ttl_is_expired(session):
    repo, company_id, session_id = session
    vehicle_id = ObjectId()
    t0 = datetime.now(timezone.utc)

    await set_active_entity(repo, company_id, session_id, "vehicle", vehicle_id, t0)
    past_ttl = t0 + timedelta(seconds=settings.active_entity_ttl_seconds + 5)

    result = await get_active_entities(repo, company_id, session_id, now=past_ttl)
    assert result == {}, "active entity older than the TTL must not resolve"


async def test_no_active_entity_set_returns_empty(session):
    repo, company_id, session_id = session
    result = await get_active_entities(repo, company_id, session_id, now=datetime.now(timezone.utc))
    assert result == {}


async def test_set_active_entity_rejects_unknown_type(session):
    repo, company_id, session_id = session
    with pytest.raises(ValueError):
        await set_active_entity(repo, company_id, session_id, "spaceship", ObjectId(), datetime.now(timezone.utc))
