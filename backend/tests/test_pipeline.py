"""
Tests the combined classify -> extract -> clarification-decision pipeline (app/nlu/pipeline.py).
CLARIFICATION_NEEDED is a downstream decision, not something the classifier emits directly from
text alone — see the module docstring for why.
"""

from datetime import datetime, timezone

import pytest_asyncio
from bson import ObjectId

from app.nlu.intent_classifier import RuleBasedIntentClassifier
from app.nlu.pipeline import analyze


@pytest_asyncio.fixture(scope="module")
async def seeded(db):
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
    return {"company_id": company_id, "vehicle_id": vehicle_id}


async def test_pronoun_with_no_active_vehicle_needs_clarification(db, seeded):
    result = await analyze(
        "what's its speed?", RuleBasedIntentClassifier(), seeded["company_id"], db, session_state={}
    )
    assert result.raw_intent == "GET_VEHICLE_SPEED"
    assert result.final_intent == "CLARIFICATION_NEEDED"
    assert "vehicle_ref" in result.unresolved_required


async def test_pronoun_with_active_vehicle_resolves_cleanly(db, seeded):
    result = await analyze(
        "what's its speed?",
        RuleBasedIntentClassifier(),
        seeded["company_id"],
        db,
        session_state={"active_entities": {"vehicle_id": seeded["vehicle_id"]}},
    )
    assert result.raw_intent == "GET_VEHICLE_SPEED"
    assert result.final_intent == "GET_VEHICLE_SPEED"
    assert result.entities["vehicle_id"] == seeded["vehicle_id"]


async def test_explicit_plate_resolves_without_clarification(db, seeded):
    result = await analyze(
        "how fast is MH12AB1234 going?", RuleBasedIntentClassifier(), seeded["company_id"], db
    )
    assert result.final_intent == "GET_VEHICLE_SPEED"
    assert result.entities["vehicle_id"] == seeded["vehicle_id"]


async def test_meta_intent_skips_entity_extraction(db, seeded):
    result = await analyze("Hi there", RuleBasedIntentClassifier(), seeded["company_id"], db)
    assert result.raw_intent == "GREETING"
    assert result.final_intent == "GREETING"
    assert result.entities == {}


async def test_bare_entity_resumes_pending_clarification(db, seeded):
    """The scripted bug: "where is my vehicle?" -> "which vehicle?" -> a bare plate number with
    no verb must complete GET_VEHICLE_LOCATION, not fall through to OUT_OF_SCOPE."""
    pending = {"intent": "GET_VEHICLE_LOCATION", "missing": "vehicle_ref"}
    result = await analyze(
        "MH12AB1234",
        RuleBasedIntentClassifier(),
        seeded["company_id"],
        db,
        session_state={"pending_clarification": pending},
    )
    assert result.raw_intent == "GET_VEHICLE_LOCATION"
    assert result.final_intent == "GET_VEHICLE_LOCATION"
    assert result.entities["vehicle_id"] == seeded["vehicle_id"]


async def test_unrelated_reply_does_not_resume_pending_clarification(db, seeded):
    """A bare reply that doesn't resolve the missing entity must not be forced into the
    pending intent — it should fall through to the classifier's own fresh verdict."""
    pending = {"intent": "GET_VEHICLE_LOCATION", "missing": "vehicle_ref"}
    result = await analyze(
        "asdf not a plate",
        RuleBasedIntentClassifier(),
        seeded["company_id"],
        db,
        session_state={"pending_clarification": pending},
    )
    assert result.raw_intent == "OUT_OF_SCOPE"


async def test_new_full_request_is_not_hijacked_by_pending_clarification(db, seeded):
    """A message that clearly expresses its own intent (matches its own trigger phrase) must
    win outright — pending-clarification resume only ever kicks in for the fallback intents
    (OUT_OF_SCOPE/GENERAL_KNOWLEDGE), never overriding a real classification."""
    pending = {"intent": "GET_VEHICLE_LOCATION", "missing": "vehicle_ref"}
    result = await analyze(
        "Hi there",
        RuleBasedIntentClassifier(),
        seeded["company_id"],
        db,
        session_state={"pending_clarification": pending},
    )
    assert result.raw_intent == "GREETING"


async def test_affirm_deny_reply_to_pending_clarification_is_not_hijacked(db, seeded):
    """"Yes"/"No" must classify as AFFIRM_DENY (via awaiting_clarification, now driven by real
    pending_clarification state) rather than being treated as an attempt to resolve the
    missing entity."""
    pending = {"intent": "GET_VEHICLE_LOCATION", "missing": "vehicle_ref"}
    result = await analyze(
        "Yes",
        RuleBasedIntentClassifier(),
        seeded["company_id"],
        db,
        session_state={"pending_clarification": pending},
    )
    assert result.raw_intent == "AFFIRM_DENY"
    assert result.final_intent == "AFFIRM_DENY"
