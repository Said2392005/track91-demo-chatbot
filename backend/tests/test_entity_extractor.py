"""
Entity extraction tests — Phase 6 testing requirement (roadmap.md: "entity extraction tests on
malformed/partial input"). Resolves against real seeded Mongo data (the `db` fixture from
conftest.py), not mocks — vehicle/driver resolution is a real repository round-trip.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from bson import ObjectId

from app.nlu.entity_extractor import extract_entities


@pytest_asyncio.fixture(scope="module")
async def seeded(db):
    company_id = ObjectId()
    other_company_id = ObjectId()
    now = datetime.now(timezone.utc)

    vehicle_mh12 = ObjectId()
    await db.vehicles.insert_one(
        {
            "_id": vehicle_mh12,
            "company_id": company_id,
            "plate_number": "MH12AB1234",
            "nickname": "Pune Van",
            "status": "active",
            "created_at": now,
        }
    )
    await db.vehicles.insert_one(
        {
            "_id": ObjectId(),
            "company_id": company_id,
            "plate_number": "MH14CD5678",
            "nickname": "Mumbai Truck 1",
            "fleet_group": "Mumbai Fleet",
            "status": "active",
            "created_at": now,
        }
    )
    # Same plate registered under a different company — must never resolve cross-tenant.
    await db.vehicles.insert_one(
        {
            "_id": ObjectId(),
            "company_id": other_company_id,
            "plate_number": "DL01GH3456",
            "status": "active",
            "created_at": now,
        }
    )

    driver_ramesh = ObjectId()
    await db.drivers.insert_one(
        {"_id": driver_ramesh, "company_id": company_id, "name": "Ramesh Kumar", "status": "active", "created_at": now}
    )
    # Name collision: a second "Ramesh Kumar" at the same company.
    await db.drivers.insert_one(
        {"_id": ObjectId(), "company_id": company_id, "name": "Ramesh Kumar", "status": "active", "created_at": now}
    )
    await db.drivers.insert_one(
        {"_id": ObjectId(), "company_id": company_id, "name": "Suresh Patil", "status": "active", "created_at": now}
    )

    return {"company_id": company_id, "vehicle_mh12": vehicle_mh12, "driver_ramesh": driver_ramesh}


async def test_lowercase_plate_resolves(db, seeded):
    result = await extract_entities(
        "what's the speed of mh12ab1234", "GET_VEHICLE_SPEED", seeded["company_id"], db
    )
    assert result.entities["vehicle_id"] == seeded["vehicle_mh12"]
    assert result.unresolved_required == []


async def test_spaced_and_hyphenated_plate_resolves(db, seeded):
    for text in ["where is mh 12 ab 1234", "where is MH-12-AB-1234", "where is MH.12.AB.1234"]:
        result = await extract_entities(text, "GET_VEHICLE_LOCATION", seeded["company_id"], db)
        assert result.entities["vehicle_id"] == seeded["vehicle_mh12"], text


async def test_nickname_resolves(db, seeded):
    result = await extract_entities(
        "where is the Pune Van right now", "GET_VEHICLE_LOCATION", seeded["company_id"], db
    )
    assert result.entities["vehicle_id"] == seeded["vehicle_mh12"]


async def test_unknown_but_validly_formatted_plate_is_unresolved(db, seeded):
    result = await extract_entities(
        "where is MH99ZZ9999", "GET_VEHICLE_LOCATION", seeded["company_id"], db
    )
    assert "vehicle_id" not in result.entities
    assert "vehicle_ref" in result.unresolved_required


async def test_plate_does_not_resolve_across_tenants(db, seeded):
    result = await extract_entities(
        "where is DL01GH3456", "GET_VEHICLE_LOCATION", seeded["company_id"], db
    )
    assert "vehicle_id" not in result.entities
    assert "vehicle_ref" in result.unresolved_required


async def test_missing_date_range_is_unresolved_even_with_vehicle_present(db, seeded):
    result = await extract_entities(
        "show trips for MH12AB1234", "GET_TRIP_HISTORY", seeded["company_id"], db
    )
    assert result.entities["vehicle_id"] == seeded["vehicle_mh12"]
    assert "date_range" not in result.entities
    assert "date_range" in result.unresolved_required


async def test_trip_history_satisfied_by_driver_alone_via_required_one_of(db, seeded):
    result = await extract_entities(
        "show trips for Suresh Patil yesterday", "GET_TRIP_HISTORY", seeded["company_id"], db
    )
    assert "driver_id" in result.entities
    assert not any(u.startswith("one_of:") for u in result.unresolved_required)


async def test_driver_name_collision_is_ambiguous_not_silently_picked(db, seeded):
    result = await extract_entities(
        "what's Ramesh Kumar's driving score this month", "GET_DRIVER_BEHAVIOR_REPORT", seeded["company_id"], db
    )
    assert "driver_id" not in result.entities
    assert "driver_ref" in result.ambiguous
    assert len(result.ambiguous["driver_ref"]) == 2


async def test_empty_utterance_does_not_crash_and_leaves_required_unresolved(db, seeded):
    result = await extract_entities("", "GET_VEHICLE_SPEED", seeded["company_id"], db)
    assert result.entities == {}
    assert "vehicle_ref" in result.unresolved_required


async def test_garbled_partial_input_does_not_crash(db, seeded):
    result = await extract_entities("uhh MH12A speed??", "GET_VEHICLE_SPEED", seeded["company_id"], db)
    # "MH12A" is not a valid plate shape (missing digits) — must not resolve, must not crash.
    assert "vehicle_id" not in result.entities
    assert "vehicle_ref" in result.unresolved_required


async def test_alert_type_synonym_sos_maps_to_panic(db, seeded):
    result = await extract_entities(
        "any SOS alerts today", "GET_ALERT_HISTORY", seeded["company_id"], db
    )
    assert result.entities["alert_type"] == "panic"


async def test_pronoun_resolves_via_active_entities(db, seeded):
    result = await extract_entities(
        "what's its speed?",
        "GET_VEHICLE_SPEED",
        seeded["company_id"],
        db,
        active_entities={"vehicle_id": seeded["vehicle_mh12"]},
    )
    assert result.entities["vehicle_id"] == seeded["vehicle_mh12"]


async def test_pronoun_without_active_entity_is_unresolved(db, seeded):
    result = await extract_entities(
        "what's its speed?", "GET_VEHICLE_SPEED", seeded["company_id"], db, active_entities=None
    )
    assert "vehicle_id" not in result.entities
    assert "vehicle_ref" in result.unresolved_required


async def test_kb_topic_passthrough_for_rag_intent(db, seeded):
    result = await extract_entities(
        "How does geofencing work?", "EXPLAIN_FEATURE", seeded["company_id"], db
    )
    assert result.entities["kb_topic"] == "How does geofencing work?"


async def test_plan_tier_ref_matches_pricing_synonym(db, seeded):
    result = await extract_entities(
        "How much does the Pro plan cost?", "PRICING", seeded["company_id"], db
    )
    assert result.entities["plan_tier_ref"] == "Pro"
