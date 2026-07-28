"""
Schema validation tests — Phase 3 testing requirement (roadmap.md).

For each collection: a valid document must insert cleanly, and a set of invalid documents
(missing required field, bad enum, malformed plate pattern) must be rejected by MongoDB's own
$jsonSchema validator, not by application-level checks.
"""

import copy
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from pymongo.errors import WriteError

NOW = datetime.now(timezone.utc)
OID = ObjectId()


def _case(collection: str, valid: dict, invalid_cases: list[tuple[str, dict]]):
    return pytest.param(collection, valid, invalid_cases, id=collection)


CASES = [
    _case(
        "companies",
        {"name": "Acme Fleets", "status": "active", "timezone": "Asia/Kolkata", "created_at": NOW},
        [("missing status", {"name": "Acme Fleets", "timezone": "Asia/Kolkata", "created_at": NOW})],
    ),
    _case(
        "users",
        {
            "company_id": OID,
            "name": "Test User",
            "email": "test@example.com",
            "role": "admin",
            "status": "active",
            "created_at": NOW,
        },
        [
            (
                "invalid role enum",
                {
                    "company_id": OID,
                    "name": "Test User",
                    "email": "test@example.com",
                    "role": "superuser",
                    "status": "active",
                    "created_at": NOW,
                },
            )
        ],
    ),
    _case(
        "vehicles",
        {"company_id": OID, "plate_number": "MH12AB1234", "status": "active", "created_at": NOW},
        [
            (
                "lowercase/unnormalized plate rejected",
                {"company_id": OID, "plate_number": "mh12ab1234", "status": "active", "created_at": NOW},
            ),
            (
                "spaced plate rejected",
                {"company_id": OID, "plate_number": "MH 12 AB 1234", "status": "active", "created_at": NOW},
            ),
            (
                "missing company_id",
                {"plate_number": "MH12AB1234", "status": "active", "created_at": NOW},
            ),
        ],
    ),
    _case(
        "drivers",
        {"company_id": OID, "name": "Ramesh Kumar", "status": "active", "created_at": NOW},
        [("invalid status enum", {"company_id": OID, "name": "Ramesh Kumar", "status": "on_leave", "created_at": NOW})],
    ),
    _case(
        "trips",
        {
            "company_id": OID,
            "vehicle_id": OID,
            "start_time": NOW,
            "end_time": NOW,
            "distance_km": 12.5,
        },
        [("missing distance_km", {"company_id": OID, "vehicle_id": OID, "start_time": NOW, "end_time": NOW})],
    ),
    _case(
        "alerts",
        {
            "company_id": OID,
            "vehicle_id": OID,
            "alert_type": "speeding",
            "triggered_at": NOW,
            "acknowledged": False,
        },
        [
            (
                "invalid alert_type enum",
                {
                    "company_id": OID,
                    "vehicle_id": OID,
                    "alert_type": "some_made_up_alert",
                    "triggered_at": NOW,
                    "acknowledged": False,
                },
            )
        ],
    ),
    _case(
        "maintenance_records",
        {"company_id": OID, "vehicle_id": OID, "service_type": "oil_change", "service_date": NOW},
        [
            (
                "invalid service_type enum",
                {"company_id": OID, "vehicle_id": OID, "service_type": "unicorn_polish", "service_date": NOW},
            )
        ],
    ),
    _case(
        "geofences",
        {
            "company_id": OID,
            "name": "Test Zone",
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]},
            "active": True,
            "created_at": NOW,
        },
        [
            (
                "invalid geometry type",
                {
                    "company_id": OID,
                    "name": "Test Zone",
                    "geometry": {"type": "Hexagon", "coordinates": []},
                    "active": True,
                    "created_at": NOW,
                },
            )
        ],
    ),
    _case(
        "chat_sessions",
        {"company_id": OID, "user_id": OID, "status": "active", "started_at": NOW, "last_active_at": NOW},
        [
            (
                "invalid status enum",
                {"company_id": OID, "user_id": OID, "status": "paused", "started_at": NOW, "last_active_at": NOW},
            )
        ],
    ),
    _case(
        "chat_messages",
        {"session_id": OID, "company_id": OID, "role": "user", "content": "hi", "created_at": NOW},
        [
            (
                "invalid role enum",
                {"session_id": OID, "company_id": OID, "role": "bot", "content": "hi", "created_at": NOW},
            )
        ],
    ),
    _case(
        "documents_meta",
        {
            "title": "Test Doc",
            "source_type": "pricing",
            "version": "v1",
            "approved_pricing": True,
            "is_active": True,
            "ingested_at": NOW,
        },
        [
            (
                "invalid source_type enum",
                {
                    "title": "Test Doc",
                    "source_type": "rumor",
                    "version": "v1",
                    "approved_pricing": True,
                    "is_active": True,
                    "ingested_at": NOW,
                },
            ),
            (
                "approved_pricing wrong type",
                {
                    "title": "Test Doc",
                    "source_type": "pricing",
                    "version": "v1",
                    "approved_pricing": "yes",
                    "is_active": True,
                    "ingested_at": NOW,
                },
            ),
        ],
    ),
]


@pytest.mark.parametrize("collection,valid_doc,invalid_cases", CASES)
async def test_valid_document_inserts(db, collection, valid_doc, invalid_cases):
    result = await db[collection].insert_one(copy.deepcopy(valid_doc))
    assert result.inserted_id is not None


@pytest.mark.parametrize("collection,valid_doc,invalid_cases", CASES)
async def test_invalid_documents_rejected(db, collection, valid_doc, invalid_cases):
    for label, bad_doc in invalid_cases:
        with pytest.raises(WriteError):
            await db[collection].insert_one(copy.deepcopy(bad_doc))
