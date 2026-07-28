"""
Graph state must be checkpoint-serializable — LangGraph's MongoDBSaver (Phase 8) serializes
state after every node via JsonPlusSerializer/ormsgpack. Verified empirically before writing
any node code: `bson.ObjectId` is NOT supported by that serializer (raises
`TypeError: Type is not msgpack serializable: ObjectId`), while `datetime` round-trips fine.

Every ID that enters AgentState is therefore a plain string, converted to/from ObjectId only at
the boundary where a node actually calls a repository or tool — never stored as ObjectId in
state itself.
"""

from bson import ObjectId


def sanitize_for_state(value):
    """Recursively convert ObjectId -> str so a value is safe to store in graph state (e.g. raw
    Mongo documents returned by MONGO_REPO tools, which nest ObjectId in _id/company_id/
    vehicle_id/driver_id fields at multiple levels)."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {k: sanitize_for_state(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_for_state(v) for v in value]
    return value


def to_object_id(value: str | None) -> ObjectId | None:
    return ObjectId(value) if value else None


def entities_to_object_ids(entities: dict) -> dict:
    """Converts the *_id fields in a resolved-entities dict back to ObjectId for repo/tool
    calls; passes non-ID entity values (date_range, kb_topic, alert_type, ...) through
    unchanged."""
    id_keys = {"vehicle_id", "driver_id", "geofence_id"}
    return {k: (to_object_id(v) if k in id_keys and v else v) for k, v in entities.items()}
