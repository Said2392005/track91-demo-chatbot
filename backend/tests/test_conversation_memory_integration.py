"""
Scripted pronoun-resolution integration test — Phase 8 requirement (roadmap.md): "user says
'MH12AB1234' then later asks 'what's its speed?' and the bot must resolve 'its' to that
vehicle." Wires together everything built so far: Phase 3 seeded vehicle data, Phase 6's
classify -> extract -> analyze pipeline, and Phase 8's SessionRepository +
active_entity_tracker — simulating two separate turns as two separate calls (not shared Python
state), the way two separate HTTP requests to the same session_id would actually work.

Also scripts the expiry case: the same scenario, but with the second turn far enough past
settings.active_entity_ttl_seconds that "its" must NOT resolve — proving expiry isn't just
configured but actually changes behavior end-to-end.
"""

from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.core.config import settings
from app.db.repositories.session_repository import SessionRepository
from app.memory.active_entity_tracker import get_active_entities, set_active_entity
from app.nlu.intent_classifier import RuleBasedIntentClassifier
from app.nlu.pipeline import analyze


async def _seed_vehicle(db):
    company_id = ObjectId()
    vehicle_id = ObjectId()
    await db.vehicles.insert_one(
        {
            "_id": vehicle_id,
            "company_id": company_id,
            "plate_number": "MH12AB1234",
            "status": "active",
            "created_at": datetime.now(timezone.utc),
        }
    )
    return company_id, vehicle_id


async def test_its_speed_resolves_to_the_previously_mentioned_vehicle(db):
    company_id, vehicle_id = await _seed_vehicle(db)
    session_repo = SessionRepository(db)
    classifier = RuleBasedIntentClassifier()
    user_id = ObjectId()

    t0 = datetime.now(timezone.utc)
    session = await session_repo.create(company_id, user_id, t0)
    session_id = session["_id"]

    # Turn 1: "Where is MH12AB1234?"
    turn1 = await analyze(
        "Where is MH12AB1234?",
        classifier,
        company_id,
        db,
        session_state={"active_entities": await get_active_entities(session_repo, company_id, session_id, now=t0)},
        now=t0,
    )
    assert turn1.final_intent == "GET_VEHICLE_LOCATION"
    assert turn1.entities["vehicle_id"] == vehicle_id

    # The orchestration layer (Phase 10, eventually) is responsible for writing back whichever
    # entity got resolved this turn — simulated explicitly here since that layer doesn't exist yet.
    await set_active_entity(session_repo, company_id, session_id, "vehicle", turn1.entities["vehicle_id"], t0)

    # Turn 2, two minutes later, as a SEPARATE call — no Python state shared with turn 1 beyond
    # session_id: "What's its speed?"
    t1 = t0 + timedelta(minutes=2)
    active_entities_turn2 = await get_active_entities(session_repo, company_id, session_id, now=t1)
    turn2 = await analyze(
        "What's its speed?",
        classifier,
        company_id,
        db,
        session_state={"active_entities": active_entities_turn2},
        now=t1,
    )

    assert turn2.raw_intent == "GET_VEHICLE_SPEED"
    assert turn2.final_intent == "GET_VEHICLE_SPEED", "must resolve cleanly, not fall to CLARIFICATION_NEEDED"
    assert turn2.entities["vehicle_id"] == vehicle_id


async def test_its_speed_does_not_resolve_once_active_entity_has_expired(db):
    company_id, vehicle_id = await _seed_vehicle(db)
    session_repo = SessionRepository(db)
    classifier = RuleBasedIntentClassifier()
    user_id = ObjectId()

    t0 = datetime.now(timezone.utc)
    session = await session_repo.create(company_id, user_id, t0)
    session_id = session["_id"]

    turn1 = await analyze(
        "Where is MH12AB1234?",
        classifier,
        company_id,
        db,
        session_state={"active_entities": await get_active_entities(session_repo, company_id, session_id, now=t0)},
        now=t0,
    )
    await set_active_entity(session_repo, company_id, session_id, "vehicle", turn1.entities["vehicle_id"], t0)

    # Turn 2, well past the active-entity TTL (but the session itself is still "open" —
    # only the active-entity reference should be treated as stale, not the whole session).
    t1 = t0 + timedelta(seconds=settings.active_entity_ttl_seconds + 60)
    active_entities_turn2 = await get_active_entities(session_repo, company_id, session_id, now=t1)
    assert active_entities_turn2 == {}, "active entity should have expired by turn 2"

    turn2 = await analyze(
        "What's its speed?",
        classifier,
        company_id,
        db,
        session_state={"active_entities": active_entities_turn2},
        now=t1,
    )

    assert turn2.raw_intent == "GET_VEHICLE_SPEED"
    assert turn2.final_intent == "CLARIFICATION_NEEDED", "expired active entity must not silently resolve 'its'"
    assert "vehicle_id" not in turn2.entities
