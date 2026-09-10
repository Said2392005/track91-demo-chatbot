"""
Intent taxonomy as code — transcribed from docs/phase-1-planning/intent-taxonomy.md. Single
source of truth: Phase 6 (entity extraction — what does this intent need to look for) and
Phase 9 (routing — which subsystem/tool handles this intent) both import from here rather than
each re-encoding the taxonomy table and risking drift.
"""

from dataclasses import dataclass, field

LIVE_API = "LIVE_API"
MONGO_REPO = "MONGO_REPO"
RAG = "RAG"
GENERAL_FALLBACK = "GENERAL_FALLBACK"
NONE_SUBSYSTEM = "NONE"


@dataclass(frozen=True)
class IntentSpec:
    subsystem: str
    required: tuple[str, ...] = ()
    required_one_of: tuple[str, ...] = ()  # at least one of these must resolve
    optional: tuple[str, ...] = ()
    mvp: bool = True


INTENT_SPECS: dict[str, IntentSpec] = {
    # A. Live data
    "GET_VEHICLE_LOCATION": IntentSpec(LIVE_API, required=("vehicle_ref",)),
    "GET_VEHICLE_SPEED": IntentSpec(LIVE_API, required=("vehicle_ref",)),
    "GET_VEHICLE_FUEL_LEVEL": IntentSpec(LIVE_API, required=("vehicle_ref",)),
    "GET_VEHICLE_HEALTH": IntentSpec(LIVE_API, required=("vehicle_ref",), optional=("metric_type",)),
    "GET_VEHICLE_IGNITION_STATUS": IntentSpec(LIVE_API, required=("vehicle_ref",)),
    "GET_FLEET_LIVE_STATUS": IntentSpec(LIVE_API, optional=("fleet_group_ref",)),
    # B. Historical data
    "GET_TRIP_HISTORY": IntentSpec(
        MONGO_REPO, required=("date_range",), required_one_of=("vehicle_ref", "driver_ref")
    ),
    "GET_TRIP_SUMMARY": IntentSpec(MONGO_REPO, required=("date_range",), optional=("vehicle_ref", "fleet_group_ref")),
    "GET_ALERT_HISTORY": IntentSpec(
        MONGO_REPO, required=("date_range",), optional=("vehicle_ref", "driver_ref", "alert_type")
    ),
    "GET_MAINTENANCE_HISTORY": IntentSpec(MONGO_REPO, required=("vehicle_ref",), optional=("date_range",)),
    "GET_MAINTENANCE_DUE": IntentSpec(MONGO_REPO, optional=("vehicle_ref", "fleet_group_ref")),
    "GET_DRIVER_BEHAVIOR_REPORT": IntentSpec(MONGO_REPO, required=("driver_ref", "date_range")),
    "GET_FUEL_CONSUMPTION_REPORT": IntentSpec(
        MONGO_REPO, required=("date_range",), optional=("vehicle_ref", "fleet_group_ref")
    ),
    "GET_GEOFENCE_LIST": IntentSpec(MONGO_REPO, optional=("vehicle_ref", "fleet_group_ref")),
    "GET_VEHICLE_ROSTER": IntentSpec(MONGO_REPO, optional=("fleet_group_ref",)),
    "GET_DRIVER_ROSTER": IntentSpec(MONGO_REPO, optional=("vehicle_ref",)),
    # C. Action / write — backlog for v1 (non-goals.md)
    "CREATE_GEOFENCE": IntentSpec(MONGO_REPO, required=("location_ref",), mvp=False),
    "ASSIGN_DRIVER_TO_VEHICLE": IntentSpec(MONGO_REPO, required=("driver_ref", "vehicle_ref"), mvp=False),
    "ACKNOWLEDGE_ALERT": IntentSpec(MONGO_REPO, required=("vehicle_ref", "alert_type"), mvp=False),
    "SCHEDULE_MAINTENANCE": IntentSpec(MONGO_REPO, required=("vehicle_ref", "date_range"), mvp=False),
    # D. Knowledge base
    "EXPLAIN_FEATURE": IntentSpec(RAG, required=("kb_topic",)),
    "EXPLAIN_ALERT_TYPE": IntentSpec(RAG, optional=("alert_type", "kb_topic")),
    "APP_FAQ": IntentSpec(RAG, required=("kb_topic",)),
    "TROUBLESHOOTING_DEVICE": IntentSpec(RAG, required=("kb_topic",)),
    "POLICY_QUESTION": IntentSpec(RAG, required=("kb_topic",)),
    "PRICING": IntentSpec(RAG, required=("kb_topic",), optional=("plan_tier_ref",)),
    "GENERAL_KNOWLEDGE": IntentSpec(GENERAL_FALLBACK, required=("kb_topic",)),
    # E. Conversational / meta
    "GREETING": IntentSpec(NONE_SUBSYSTEM),
    "GOODBYE": IntentSpec(NONE_SUBSYSTEM),
    "CHITCHAT": IntentSpec(NONE_SUBSYSTEM),
    # Added after real testing: "is Track91 a GPS app?" / "what is Track91" / "what does your
    # company do" were previously left to refuse (OUT_OF_SCOPE) or, worse, fall through to
    # GENERAL_KNOWLEDGE's generic "GPS apps in general" answer — confusingly unhelpful for a
    # question specifically about this product. See docs/phase-1-planning/intent-taxonomy.md's
    # note on this reversal.
    "ABOUT_TRACK91": IntentSpec(NONE_SUBSYSTEM),
    "CLARIFICATION_NEEDED": IntentSpec(NONE_SUBSYSTEM),
    "AFFIRM_DENY": IntentSpec(NONE_SUBSYSTEM),
    "OUT_OF_SCOPE": IntentSpec(NONE_SUBSYSTEM),
}

ALL_INTENTS = tuple(INTENT_SPECS.keys())
MVP_INTENTS = tuple(name for name, spec in INTENT_SPECS.items() if spec.mvp)
