"""
JSON Schema validators for every MongoDB collection, per docs/phase-3-database/schema-design.md.

Enums defined here are the single source of truth — Phase 6 (entity extraction) and Phase 9
(tool routing) must import from this module rather than redefining these lists.
"""

VEHICLE_PLATE_PATTERN = r"^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$"
"""Canonical normalized plate form — see docs/phase-1-planning/entity-taxonomy.md's
`vehicle_ref` normalization rule. Callers must normalize (strip/uppercase/de-separate) BEFORE
writing plate_number; this pattern is a backstop, not a substitute for that step."""

ALERT_TYPES = [
    "speeding",
    "harsh_braking",
    "harsh_acceleration",
    "idle",
    "panic",
    "geofence_entry",
    "geofence_exit",
    "low_fuel",
    "device_offline",
    "maintenance_due",
]

ALERT_SEVERITIES = ["low", "medium", "high"]

COMPANY_STATUSES = ["trial", "active", "suspended"]
USER_ROLES = ["admin", "fleet_manager", "dispatcher"]
USER_STATUSES = ["active", "disabled"]
VEHICLE_STATUSES = ["active", "inactive", "decommissioned"]
DRIVER_STATUSES = ["active", "inactive"]
MAINTENANCE_SERVICE_TYPES = [
    "oil_change",
    "tire_rotation",
    "brake_service",
    "battery_replacement",
    "inspection",
    "general_service",
    "other",
]
CHAT_SESSION_STATUSES = ["active", "closed"]
CHAT_MESSAGE_ROLES = ["user", "assistant", "system"]

# Maps 1:1 to the Phase 1 knowledge-base intents (intent-taxonomy.md section D), minus
# GENERAL_KNOWLEDGE which is explicitly never backed by an ingested KB document.
DOCUMENT_SOURCE_TYPES = [
    "feature_guide",  # EXPLAIN_FEATURE
    "app_faq",  # APP_FAQ
    "troubleshooting",  # TROUBLESHOOTING_DEVICE
    "policy",  # POLICY_QUESTION
    "pricing",  # PRICING — approved_pricing flag on these docs gates the PRICING intent
]

_OBJECT_ID = {"bsonType": "objectId"}
_STRING = {"bsonType": "string"}
_DATE = {"bsonType": "date"}
_BOOL = {"bsonType": "bool"}
_DOUBLE = {"bsonType": ["double", "int"]}


def _schema(title: str, required: list[str], properties: dict) -> dict:
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "title": title,
            "required": required,
            "properties": {"_id": _OBJECT_ID, **properties},
        }
    }


COLLECTION_VALIDATORS: dict[str, dict] = {
    "companies": _schema(
        "Company",
        required=["name", "status", "timezone", "created_at"],
        properties={
            "name": _STRING,
            "status": {"enum": COMPANY_STATUSES},
            "timezone": _STRING,  # IANA tz name, e.g. "Asia/Kolkata" — default per non-goals.md
            "created_at": _DATE,
        },
    ),
    "users": _schema(
        "User",
        required=["company_id", "name", "email", "role", "status", "created_at"],
        properties={
            "company_id": _OBJECT_ID,
            "name": _STRING,
            "email": _STRING,
            "role": {"enum": USER_ROLES},
            "status": {"enum": USER_STATUSES},
            "password_hash": _STRING,
            "created_at": _DATE,
        },
    ),
    "vehicles": _schema(
        "Vehicle",
        required=["company_id", "plate_number", "status", "created_at"],
        properties={
            "company_id": _OBJECT_ID,
            "plate_number": {**_STRING, "pattern": VEHICLE_PLATE_PATTERN},
            "nickname": _STRING,
            "make": _STRING,
            "model": _STRING,
            "year": {"bsonType": "int"},
            "vehicle_type": _STRING,
            "fleet_group": _STRING,
            "assigned_driver_id": _OBJECT_ID,
            "device_id": _STRING,
            "status": {"enum": VEHICLE_STATUSES},
            "created_at": _DATE,
            "updated_at": _DATE,
        },
    ),
    "drivers": _schema(
        "Driver",
        required=["company_id", "name", "status", "created_at"],
        properties={
            "company_id": _OBJECT_ID,
            "name": _STRING,
            "phone": _STRING,
            "license_number": _STRING,
            "status": {"enum": DRIVER_STATUSES},
            "created_at": _DATE,
        },
    ),
    "trips": _schema(
        "Trip",
        required=["company_id", "vehicle_id", "start_time", "end_time", "distance_km"],
        properties={
            "company_id": _OBJECT_ID,
            "vehicle_id": _OBJECT_ID,
            "driver_id": _OBJECT_ID,
            "start_time": _DATE,
            "end_time": _DATE,
            "start_location": {
                "bsonType": "object",
                "properties": {"lat": _DOUBLE, "lng": _DOUBLE, "address": _STRING},
            },
            "end_location": {
                "bsonType": "object",
                "properties": {"lat": _DOUBLE, "lng": _DOUBLE, "address": _STRING},
            },
            "distance_km": _DOUBLE,
            "duration_minutes": _DOUBLE,
            "stop_count": {"bsonType": "int"},
            "avg_speed_kmph": _DOUBLE,
            "max_speed_kmph": _DOUBLE,
            "created_at": _DATE,
        },
    ),
    "alerts": _schema(
        "Alert",
        required=["company_id", "vehicle_id", "alert_type", "triggered_at", "acknowledged"],
        properties={
            "company_id": _OBJECT_ID,
            "vehicle_id": _OBJECT_ID,
            "driver_id": _OBJECT_ID,
            "alert_type": {"enum": ALERT_TYPES},
            "severity": {"enum": ALERT_SEVERITIES},
            "triggered_at": _DATE,
            "location": {
                "bsonType": "object",
                "properties": {"lat": _DOUBLE, "lng": _DOUBLE},
            },
            "details": _STRING,
            "acknowledged": _BOOL,
            "acknowledged_at": _DATE,
            "acknowledged_by": _OBJECT_ID,
            "created_at": _DATE,
        },
    ),
    "maintenance_records": _schema(
        "MaintenanceRecord",
        required=["company_id", "vehicle_id", "service_type", "service_date"],
        properties={
            "company_id": _OBJECT_ID,
            "vehicle_id": _OBJECT_ID,
            "service_type": {"enum": MAINTENANCE_SERVICE_TYPES},
            "service_date": _DATE,
            "odometer_km": _DOUBLE,
            "cost": _DOUBLE,
            "notes": _STRING,
            "next_due_date": _DATE,
            "next_due_odometer_km": _DOUBLE,
            "created_at": _DATE,
        },
    ),
    "geofences": _schema(
        "Geofence",
        required=["company_id", "name", "geometry", "active", "created_at"],
        properties={
            "company_id": _OBJECT_ID,
            "name": _STRING,
            "geometry": {
                "bsonType": "object",
                "required": ["type", "coordinates"],
                "properties": {
                    "type": {"enum": ["Polygon", "Point"]},
                    "coordinates": {"bsonType": "array"},
                },
            },
            "vehicle_ids": {"bsonType": "array", "items": _OBJECT_ID},
            "fleet_group": _STRING,
            "active": _BOOL,
            "created_at": _DATE,
        },
    ),
    "chat_sessions": _schema(
        "ChatSession",
        required=["company_id", "user_id", "status", "started_at", "last_active_at"],
        properties={
            "company_id": _OBJECT_ID,
            "user_id": _OBJECT_ID,
            "status": {"enum": CHAT_SESSION_STATUSES},
            "started_at": _DATE,
            "last_active_at": _DATE,
            "active_entities": {
                "bsonType": "object",
                "properties": {
                    "vehicle_id": _OBJECT_ID,
                    "driver_id": _OBJECT_ID,
                    "geofence_id": _OBJECT_ID,
                },
            },
            # Phase 8: when active_entities was last written. Coreference resolution treats
            # active_entities as expired (ignores them) once this is older than
            # settings.active_entity_ttl_seconds — see app/memory/active_entity_tracker.py.
            "active_entities_updated_at": _DATE,
            # Set by clarify_node when route() asks a clarifying question; popped (read once,
            # then cleared) by entry_node on the very next turn — single-turn scoped by
            # construction, not TTL-based. Lets a bare follow-up like "MH12AB1234" (no verb)
            # complete the intent that was waiting on it instead of falling through to
            # OUT_OF_SCOPE. See app/nlu/pipeline.py's analyze().
            "pending_clarification": {
                "bsonType": "object",
                "properties": {
                    "intent": _STRING,
                    "missing": _STRING,
                },
            },
        },
    ),
    "chat_messages": _schema(
        "ChatMessage",
        required=["session_id", "company_id", "role", "content", "created_at"],
        properties={
            "session_id": _OBJECT_ID,
            "company_id": _OBJECT_ID,
            "role": {"enum": CHAT_MESSAGE_ROLES},
            "content": _STRING,
            "intent": _STRING,
            "entities": {"bsonType": "object"},
            "tool_called": _STRING,
            "created_at": _DATE,
        },
    ),
    "documents_meta": _schema(
        "DocumentMeta",
        required=["title", "source_type", "version", "approved_pricing", "is_active", "ingested_at"],
        properties={
            "title": _STRING,
            "source_type": {"enum": DOCUMENT_SOURCE_TYPES},
            "original_filename": _STRING,
            "version": _STRING,
            "approved_pricing": _BOOL,  # PRICING gate flag — see ADR/sequence-diagrams.md #4
            "is_active": _BOOL,
            "checksum": _STRING,
            "chunk_count": {"bsonType": "int"},
            "ingested_at": _DATE,
        },
    ),
}
