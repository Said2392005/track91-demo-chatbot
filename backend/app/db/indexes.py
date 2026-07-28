"""
Index definitions per collection.

Rule (ADR 004, docs/phase-2-architecture/adr/004-tenant-scoping-enforcement.md): every
compound index on tenant-scoped data leads with `company_id`, so tenant scoping is also the
performant access path, not just a correctness constraint.
"""

from pymongo import ASCENDING, GEOSPHERE

# Each entry: (keys: list[(field, direction)], options: dict)
INDEX_DEFINITIONS: dict[str, list[tuple[list[tuple[str, int]], dict]]] = {
    "companies": [
        ([("name", ASCENDING)], {"name": "name_idx"}),
    ],
    "users": [
        ([("email", ASCENDING)], {"name": "email_unique", "unique": True}),
        ([("company_id", ASCENDING)], {"name": "company_idx"}),
    ],
    "vehicles": [
        (
            [("company_id", ASCENDING), ("plate_number", ASCENDING)],
            {"name": "company_plate_unique", "unique": True},
        ),
        (
            # NOT `sparse: True` — on a COMPOUND index, sparse only skips docs missing *all*
            # indexed fields, and company_id is always present, so sparse alone doesn't skip
            # vehicles missing just device_id (a real state: a vehicle can exist before a GPS
            # device is registered to it, per kb_sources/app_faq/track91-app-faq.md). Without
            # partialFilterExpression, two such vehicles at the same company collide on
            # device_id: null. Caught by tests/test_entity_extractor.py's seed fixture.
            [("company_id", ASCENDING), ("device_id", ASCENDING)],
            {
                "name": "company_device_unique",
                "unique": True,
                "partialFilterExpression": {"device_id": {"$exists": True}},
            },
        ),
        (
            [("company_id", ASCENDING), ("assigned_driver_id", ASCENDING)],
            {"name": "company_driver_idx"},
        ),
    ],
    "drivers": [
        ([("company_id", ASCENDING)], {"name": "company_idx"}),
        (
            # Same compound-sparse pitfall as vehicles.company_device_unique above — see the
            # comment there. partialFilterExpression, not sparse, is what actually excludes
            # drivers missing license_number from the uniqueness constraint.
            [("company_id", ASCENDING), ("license_number", ASCENDING)],
            {
                "name": "company_license_unique",
                "unique": True,
                "partialFilterExpression": {"license_number": {"$exists": True}},
            },
        ),
    ],
    "trips": [
        (
            [("company_id", ASCENDING), ("vehicle_id", ASCENDING), ("start_time", ASCENDING)],
            {"name": "company_vehicle_time_idx"},
        ),
        (
            [("company_id", ASCENDING), ("driver_id", ASCENDING), ("start_time", ASCENDING)],
            {"name": "company_driver_time_idx"},
        ),
    ],
    "alerts": [
        (
            [("company_id", ASCENDING), ("vehicle_id", ASCENDING), ("triggered_at", ASCENDING)],
            {"name": "company_vehicle_time_idx"},
        ),
        (
            [("company_id", ASCENDING), ("alert_type", ASCENDING), ("triggered_at", ASCENDING)],
            {"name": "company_type_time_idx"},
        ),
        (
            [("company_id", ASCENDING), ("acknowledged", ASCENDING)],
            {"name": "company_ack_idx"},
        ),
    ],
    "maintenance_records": [
        (
            [("company_id", ASCENDING), ("vehicle_id", ASCENDING), ("service_date", ASCENDING)],
            {"name": "company_vehicle_service_idx"},
        ),
        (
            [("company_id", ASCENDING), ("next_due_date", ASCENDING)],
            {"name": "company_due_idx"},
        ),
    ],
    "geofences": [
        ([("company_id", ASCENDING), ("active", ASCENDING)], {"name": "company_active_idx"}),
        ([("geometry", GEOSPHERE)], {"name": "geometry_2dsphere"}),
    ],
    "chat_sessions": [
        (
            [("company_id", ASCENDING), ("user_id", ASCENDING), ("last_active_at", ASCENDING)],
            {"name": "company_user_activity_idx"},
        ),
    ],
    "chat_messages": [
        ([("session_id", ASCENDING), ("created_at", ASCENDING)], {"name": "session_time_idx"}),
        ([("company_id", ASCENDING), ("created_at", ASCENDING)], {"name": "company_time_idx"}),
    ],
    "documents_meta": [
        ([("source_type", ASCENDING)], {"name": "source_type_idx"}),
        ([("approved_pricing", ASCENDING)], {"name": "approved_pricing_idx"}),
        (
            [("title", ASCENDING), ("version", ASCENDING)],
            {"name": "title_version_unique", "unique": True},
        ),
    ],
}
