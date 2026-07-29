"""
Small golden set for app/nlu/message_splitter.py — measures the false-split rate on cases
specifically chosen to be tricky for a naive "split on and/also" rule, before that rule is
trusted anywhere near the main pipeline.

Negatives (should_split=False) are grounded in real content, not invented to be unrealistically
hard: "How long is trip and location history retained?" is the literal utterance from
app/eval/golden_set.py's policy_1 case (POLICY_QUESTION); the app_faq case's phrasing mirrors
kb_sources/app_faq/track91-app-faq.md's actual registration answer ("...link the device to, or
choose Unassigned to register it without linking yet"), which is one coherent question about one
FAQ entry, not two.

Positives (should_split=True) are the shape of request this splitter exists for: two
independently-routable intents joined by "and"/"also".
"""

from dataclasses import dataclass


@dataclass
class SplitterCase:
    case_id: str
    utterance: str
    should_split: bool
    note: str = ""


SPLITTER_GOLDEN_SET: list[SplitterCase] = [
    # --- Negatives: must NOT split (7) ---
    SplitterCase(
        "neg_explain_feature_and",
        "What happens when a vehicle enters and exits a geofence?",
        should_split=False,
        note='"and" joins two verbs describing one EXPLAIN_FEATURE question, not two intents — '
        "splitting breaks kb_topic (entity_extractor.py sets kb_topic to the whole utterance).",
    ),
    SplitterCase(
        "neg_two_drivers",
        "Show trips for Ramesh and Suresh",
        should_split=False,
        note="one GET_TRIP_HISTORY intent, two drivers — not two intents.",
    ),
    SplitterCase(
        "neg_policy_compound_noun",
        "How long is trip and location history retained?",
        should_split=False,
        note='literal utterance from app/eval/golden_set.py\'s "policy_1" case — "trip and '
        'location history" is a compound noun phrase, not two clauses.',
    ),
    SplitterCase(
        "neg_two_vehicles",
        "Show trips for MH12AB1234 and MH14CD5678",
        should_split=False,
        note="one GET_TRIP_HISTORY intent, two vehicles.",
    ),
    SplitterCase(
        "neg_two_drivers_score",
        "What's Ramesh Kumar and Suresh Patil's driving score this month?",
        should_split=False,
        note="one GET_DRIVER_BEHAVIOR_REPORT intent, two drivers.",
    ),
    SplitterCase(
        "neg_health_compound_verb",
        "Is MH12AB1234's engine ok and running smoothly?",
        should_split=False,
        note="one GET_VEHICLE_HEALTH question describing a single condition two ways.",
    ),
    SplitterCase(
        "neg_app_faq_register_and_link",
        "How do I register a new GPS device and link it to a vehicle?",
        should_split=False,
        note="mirrors kb_sources/app_faq/track91-app-faq.md's actual registration answer — "
        "registering and linking are the same FAQ entry, one APP_FAQ question.",
    ),
    # --- Positives: SHOULD split (6) ---
    SplitterCase(
        "pos_drivers_and_locations",
        "list my drivers and also show vehicle locations",
        should_split=True,
        note="the motivating example: GET_DRIVER_ROSTER + GET_VEHICLE_LOCATION.",
    ),
    SplitterCase(
        "pos_location_and_speed",
        "Where is MH12AB1234 and what's its speed?",
        should_split=True,
        note="GET_VEHICLE_LOCATION + GET_VEHICLE_SPEED, same vehicle.",
    ),
    SplitterCase(
        "pos_trips_and_maintenance",
        "Show trip history for MH12AB1234 and also check maintenance due",
        should_split=True,
        note="GET_TRIP_HISTORY + GET_MAINTENANCE_DUE.",
    ),
    SplitterCase(
        "pos_vehicles_and_drivers",
        "List all vehicles and also list all drivers",
        should_split=True,
        note="GET_VEHICLE_ROSTER + GET_DRIVER_ROSTER.",
    ),
    SplitterCase(
        "pos_alerts_and_moving",
        "Any alerts for MH12AB1234 this month and also is it currently moving?",
        should_split=True,
        note="GET_ALERT_HISTORY + GET_FLEET_LIVE_STATUS-shaped live check.",
    ),
    SplitterCase(
        "pos_geofencing_and_pricing",
        "How does geofencing work and also what's included in the Enterprise plan?",
        should_split=True,
        note="EXPLAIN_FEATURE + PRICING — two different subsystems entirely (RAG twice, but two separate KB lookups).",
    ),
]
