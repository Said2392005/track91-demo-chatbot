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
