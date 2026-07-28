"""
Trigger phrase/regex tables for RuleBasedIntentClassifier — one entry per intent in
app/core/taxonomy.py (except CLARIFICATION_NEEDED and AFFIRM_DENY, which are dialogue-state
driven rather than text-triggered, and GENERAL_KNOWLEDGE/OUT_OF_SCOPE, which are fallback
outcomes rather than positively triggered).

Scoring: a matched phrase scores by its word count (longer/more specific phrases outweigh short
generic ones); a matched regex scores a flat 3. Ties break by category priority order — the
order intents are declared in app/core/taxonomy.py (A live -> B history -> C backlog actions ->
D knowledge base -> E meta), matching the Phase 2 architecture's stated routing priority.
"""

import re

TRIGGER_PHRASES: dict[str, list[str]] = {
    # A. Live data
    "GET_VEHICLE_LOCATION": [
        "where is",
        "where's",
        "current location",
        "location of",
        "track my vehicle",
        "find my vehicle",
        "where can i find",
    ],
    "GET_VEHICLE_SPEED": [
        "how fast",
        "current speed",
        "its speed",
        "speed right now",
        "going at what speed",
        "what speed is",
    ],
    "GET_VEHICLE_FUEL_LEVEL": [
        "fuel level",
        "how much fuel",
        "fuel left",
        "gas level",
        "petrol level",
        "fuel remaining",
    ],
    "GET_VEHICLE_HEALTH": [
        "engine warning",
        "engine warnings",
        "engine ok",
        "any issues with",
        "diagnostic",
        "check engine",
        "vehicle healthy",
        "health status",
    ],
    "GET_VEHICLE_IGNITION_STATUS": [
        "is it on or off",
        "ignition status",
        "is the ignition",
        "engine on or off",
        "is it running",
        "is it moving or parked",
        "on or off right now",
    ],
    "GET_FLEET_LIVE_STATUS": [
        "how many vehicles are moving",
        "live status of my fleet",
        "fleet status right now",
        "vehicles active now",
        "vehicles are active",
        "how many are idle right now",
        "current fleet status",
    ],
    # B. Historical data
    "GET_TRIP_HISTORY": [
        "trip history",
        "show trips",
        "list of trips",
        "trips yesterday",
        "trips last week",
        "journeys made",
        "journeys did",
        "show me trips",
    ],
    "GET_TRIP_SUMMARY": [
        "how many km",
        "total distance",
        "distance covered",
        "km covered",
        "trip summary",
        "kilometers driven",
    ],
    "GET_ALERT_HISTORY": [
        "any alerts",
        "alert history",
        "list of alerts",
        "alerts this month",
        "alerts today",
        "past alerts",
    ],
    "GET_MAINTENANCE_HISTORY": [
        "last serviced",
        "service history",
        "when was it serviced",
        "maintenance history",
        "last service",
        "when was the last service",
    ],
    "GET_MAINTENANCE_DUE": [
        "due for service",
        "service due",
        "which vehicles need service",
        "maintenance due",
        "due for maintenance",
        "upcoming service",
        "overdue for maintenance",
    ],
    "GET_DRIVER_BEHAVIOR_REPORT": [
        "driving score",
        "driver score",
        "behavior report",
        "driving behavior",
        "harsh events",
        "driver scorecard",
    ],
    "GET_FUEL_CONSUMPTION_REPORT": [
        "fuel report",
        "fuel efficiency",
        "fuel consumption",
        "mileage report",
        "fuel efficiency report",
    ],
    "GET_GEOFENCE_LIST": [
        "geofences apply",
        "which geofences",
        "list geofences",
        "geofences for",
        "geofence list",
        "what geofences",
    ],
    "GET_VEHICLE_ROSTER": [
        "list all vehicles",
        "all my vehicles",
        "vehicle list",
        "show vehicles",
        "fleet roster",
        "show me my vehicles",
    ],
    "GET_DRIVER_ROSTER": [
        "list all drivers",
        "all drivers",
        "driver list",
        "who drives",
        "show drivers",
        "show me my drivers",
    ],
    # C. Action / write (backlog for v1, still classifiable)
    "CREATE_GEOFENCE": [
        "create a geofence",
        "add a geofence",
        "new geofence",
        "set up a geofence",
        "draw a geofence",
        "make a geofence",
    ],
    "ASSIGN_DRIVER_TO_VEHICLE": [
        "assign driver",
        "assign him to",
        "assign her to",
        "make him the driver of",
        "set the driver for",
        "assign a driver to",
    ],
    "ACKNOWLEDGE_ALERT": [
        "acknowledge the alert",
        "acknowledge alert",
        "mark alert as",
        "dismiss the alert",
        "clear the alert",
        "acknowledge this alert",
        "mark this alert",
        "mark the alert",
    ],
    "SCHEDULE_MAINTENANCE": [
        "schedule a service",
        "book a service",
        "schedule maintenance",
        "arrange a service",
        "set up a service appointment",
    ],
    # D. Knowledge base
    "EXPLAIN_FEATURE": [
        "how does geofencing work",
        "what does the driver score mean",
        "what is geofencing",
        "how does tracking work",
        "explain how",
    ],
    "EXPLAIN_ALERT_TYPE": [
        "what counts as",
        "what is harsh braking",
        "harsh braking",
        "why did i get a",
        "what triggers a",
    ],
    "APP_FAQ": [
        "how do i add",
        "how do i register",
        "how do i generate",
        "how do i export",
        "how do i create",
        "how to add",
        "how to register",
        "how to generate",
    ],
    "TROUBLESHOOTING_DEVICE": [
        "device offline",
        "gps not updating",
        "device shows offline",
        "not connecting",
        "isn't connecting",
        "device not working",
        "gps not working",
        "isn't working",
        "is not updating",
        "isn't updating",
        "device stopped sending",
    ],
    "POLICY_QUESTION": [
        "how long is",
        "data retention",
        "how long do you keep",
        "what happens to my data",
        "retention policy",
        "how long are",
    ],
    "PRICING": [
        "how much does",
        "cost per month",
        "the price",
        "pricing for",
        "plan cost",
        "discount for",
        "how much is the",
    ],
    # E. Conversational / meta
    "GREETING": ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"],
    "GOODBYE": ["bye", "goodbye", "see you", "that's all thanks", "thank you bye", "that's all for now"],
    "CHITCHAT": ["how are you", "what can you do", "who are you", "tell me a joke", "what's up"],
}

TRIGGER_REGEXES: dict[str, list[re.Pattern]] = {
    # "alert" is mandatory here, not optional — "what does X mean" alone must NOT match (it
    # would otherwise swallow general-knowledge term questions like "what does AIS-140 mean?").
    "EXPLAIN_ALERT_TYPE": [re.compile(r"what does .+ alert mean")],
    "PRICING": [re.compile(r"\bcost\b"), re.compile(r"\bprice\b"), re.compile(r"\bpricing\b")],
    "ASSIGN_DRIVER_TO_VEHICLE": [re.compile(r"\bassign \w+ to\b")],
    "ACKNOWLEDGE_ALERT": [re.compile(r"\backnowledge .*alert"), re.compile(r"\bmark (this |the )?alert\b")],
}

# Order-independent co-occurrence check: score if the utterance contains AT LEAST ONE phrase
# from each list, anywhere, in any order — not adjacent, not a fixed sentence structure.
# Replaces an earlier fixed-phrase/regex-only approach for these two intents, which proved too
# rigid: a single fixed pattern per intent either over-matched general-knowledge questions
# ("how does GPS triangulation work?") or under-matched realistic rephrasings ("What's
# geofencing?", "Can you tell me how geofencing works?", "Can you explain what the panic alert
# means?") — both failure modes were caught empirically, not assumed.
TRIGGER_COOCCURRENCE: dict[str, tuple[list[str], list[str]]] = {
    "EXPLAIN_FEATURE": (
        ["how does", "how do", "what is", "what's", "explain", "tell me", "understand how", "used for"],
        [
            "geofencing",
            "geofence",
            "tracking",
            "driver scoring",
            "driver score",
            "alert system",
            "maintenance reminder",
            "live status",
        ],
    ),
    "EXPLAIN_ALERT_TYPE": (
        ["what does", "what is", "why did i get", "why would i", "why did i receive", "explain"],
        [
            "alert",
            "harsh braking",
            "harsh acceleration",
            "speeding",
            "panic",
            "low fuel",
            "geofence entry",
            "geofence exit",
            "idle",
            "device offline",
        ],
    ),
}

AFFIRM_DENY_PHRASES = [
    "yes",
    "yeah",
    "yep",
    "correct",
    "that one",
    "that's right",
    "no",
    "nope",
    "not that one",
    "the other one",
    "wrong one",
]

DOMAIN_ADJACENT_KEYWORDS = [
    "gps",
    "fleet",
    "vehicle",
    "tracking",
    "telematics",
    "ais-140",
    "ais 140",
    "odometer",
    "geofenc",
    "obd",
    "sim",
    "device",
]
