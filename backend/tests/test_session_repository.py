from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.db.repositories.session_repository import SessionRepository


async def test_create_and_get(db):
    repo = SessionRepository(db)
    company_id, user_id = ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)

    created = await repo.create(company_id, user_id, now)
    fetched = await repo.get(company_id, created["_id"])

    assert fetched is not None
    assert fetched["status"] == "active"
    assert fetched["company_id"] == company_id


async def test_get_scoped_to_company_returns_none_for_other_company(db):
    repo = SessionRepository(db)
    company_id, other_company_id, user_id = ObjectId(), ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)

    created = await repo.create(company_id, user_id, now)
    assert await repo.get(other_company_id, created["_id"]) is None


async def test_touch_updates_last_active_at(db):
    repo = SessionRepository(db)
    company_id, user_id = ObjectId(), ObjectId()
    t0 = datetime.now(timezone.utc)
    created = await repo.create(company_id, user_id, t0)

    t1 = t0 + timedelta(minutes=5)
    await repo.touch(company_id, created["_id"], t1)

    fetched = await repo.get(company_id, created["_id"])
    # MongoDB stores dates at millisecond precision; datetime.now() has microsecond precision,
    # so exact equality after a round-trip is too strict — compare with millisecond tolerance.
    assert abs((fetched["last_active_at"] - t1).total_seconds()) < 0.001


async def test_set_active_entity_then_get(db):
    repo = SessionRepository(db)
    company_id, user_id, vehicle_id = ObjectId(), ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)
    created = await repo.create(company_id, user_id, now)

    await repo.set_active_entity(company_id, created["_id"], "vehicle", vehicle_id, now)

    active_entities, updated_at = await repo.get_active_entities(company_id, created["_id"])
    assert active_entities["vehicle_id"] == vehicle_id
    assert abs((updated_at - now).total_seconds()) < 0.001  # millisecond precision, see above


async def test_set_active_entity_replaces_not_stacks(db):
    """Last-reference-wins, per session_repository.py's resolution of the open question in
    entity-taxonomy.md: asking about a second vehicle replaces the first as "active", it
    doesn't keep both."""
    repo = SessionRepository(db)
    company_id, user_id = ObjectId(), ObjectId()
    vehicle_a, vehicle_b = ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)
    created = await repo.create(company_id, user_id, now)

    await repo.set_active_entity(company_id, created["_id"], "vehicle", vehicle_a, now)
    await repo.set_active_entity(company_id, created["_id"], "vehicle", vehicle_b, now)

    active_entities, _ = await repo.get_active_entities(company_id, created["_id"])
    assert active_entities["vehicle_id"] == vehicle_b


async def test_get_active_entities_for_unknown_session_returns_empty(db):
    repo = SessionRepository(db)
    active_entities, updated_at = await repo.get_active_entities(ObjectId(), ObjectId())
    assert active_entities == {}
    assert updated_at is None
