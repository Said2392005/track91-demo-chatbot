"""
Intent classifier unit tests — Phase 6 testing requirement (roadmap.md: "5+ paraphrases per
intent"). Tests RuleBasedIntentClassifier, the default strategy (settings.intent_classifier_strategy
== "rule_based") — fully offline, no API key or network access needed.

Paraphrases are realistic user phrasings, not copies of the trigger phrases in
trigger_patterns.py — they were run against the classifier and trigger_patterns.py was tuned
until all of them passed, rather than reverse-engineering phrasings to match the code.
"""

import pytest

from app.nlu.intent_classifier import RuleBasedIntentClassifier

PARAPHRASES: dict[str, list[str]] = {
    "GET_VEHICLE_LOCATION": [
        "Where is MH12AB1234 right now?",
        "What's the current location of the Pune van?",
        "Can you track my vehicle MH12AB1234 for me?",
        "Where's MH14CD5678 at the moment?",
        "Find my vehicle MH12AB1234",
        # Regression: found via the systematic 41-probe realistic-paraphrase check, fixed with
        # a GET_VEHICLE_LOCATION cooccurrence table + bare-plate regexes.
        "Locate MH12AB1234",
        "MH12AB1234's location",
        "Can you find MH12AB1234?",
        # Regression: found building the dual-intent detector's eval set — "vehicle
        # location(s)" as a bare noun phrase (no verb, no plate) scored 0.
        "Show vehicle location",
        "Show vehicle locations",
        # Regression: found via the all-intent systematic trigger-coverage probe — bare
        # "location" alone.
        "location",
        "Show me MH12AB1234's whereabouts",
    ],
    "GET_VEHICLE_SPEED": [
        "How fast is MH12AB1234 going?",
        "What's its speed?",
        "What's the current speed of the truck?",
        "What speed is MH14CD5678 doing right now?",
        "How fast is it going right now?",
        # Regression: found via live testing, fell through to GENERAL_KNOWLEDGE before the
        # "vehicle speed"/"speed of" trigger phrases were added.
        "What is my vehicle speed?",
        "What is the speed of my vehicle?",
        # Regression: found via the systematic 41-probe realistic-paraphrase check, fixed with
        # a GET_VEHICLE_SPEED cooccurrence table + a bare-plate regex.
        "MH12AB1234 speed",
        "How quickly is MH12AB1234 moving?",
        # Regression: found via the all-intent systematic trigger-coverage probe — bare "speed"
        # alone, and "how quick" (no "-ly") wasn't in the cooccurrence verb list.
        "speed",
        "How quick is it moving right now?",
    ],
    "GET_VEHICLE_FUEL_LEVEL": [
        "What's the fuel level on MH12AB1234?",
        "How much fuel does it have left?",
        "How much fuel is left in the tank?",
        "Check the gas level for MH14CD5678",
        "How much petrol level is left?",
        # Regression: found via the systematic 41-probe realistic-paraphrase check, fixed with
        # a GET_VEHICLE_FUEL_LEVEL cooccurrence table + a bare-plate regex.
        "MH12AB1234 fuel",
        "How much petrol does MH12AB1234 have?",
        "Fuel percentage of MH12AB1234",
        # Regression: found via live testing right after the fix above — the bare-plate regex
        # only handled the possessive ("'s") for GET_VEHICLE_LOCATION at first; "MH12AB1234's
        # fuel" fell through the same way "MH12AB1234's location" would have.
        "MH12AB1234's fuel",
        # Regression: found via the all-intent systematic trigger-coverage probe — "status"
        # wasn't in the cooccurrence subject list, and the topic-word-before-plate order isn't
        # covered by the bare-plate regex either.
        "Fuel status of MH12AB1234",
    ],
    "GET_VEHICLE_HEALTH": [
        "Any engine warnings on MH12AB1234?",
        "Is the vehicle healthy?",
        "Can you run a diagnostic on it?",
        "Is the engine ok?",
        "Any issues with MH14CD5678 right now?",
        # Regression: found via the all-intent systematic trigger-coverage probe (see
        # docs/phase-6-semantic-analysis/known-gaps.md) — all four fell through to OUT_OF_SCOPE
        # before the fix.
        "Is MH12AB1234 healthy?",
        "MH12AB1234 diagnostics",
        "Any problems with MH12AB1234?",
        "engine health",
    ],
    "GET_VEHICLE_IGNITION_STATUS": [
        "Is MH12AB1234 on or off right now?",
        "Is it running right now?",
        "What's the ignition status?",
        "Is the engine on or off?",
        "Is it moving or parked right now?",
        # Regression: found via the all-intent systematic trigger-coverage probe.
        "Is MH12AB1234 turned on?",
        "MH12AB1234 ignition",
    ],
    "GET_FLEET_LIVE_STATUS": [
        "How many vehicles are moving right now?",
        "What's the live status of my fleet?",
        "Give me the current fleet status",
        "How many vehicles are active now?",
        "How many are idle right now?",
        # Regression: found via the all-intent systematic trigger-coverage probe — all three
        # fell through to GENERAL_KNOWLEDGE (the "fleet" DOMAIN_ADJACENT_KEYWORDS fallback)
        # before the fix.
        "What's my fleet status?",
        "Number of vehicles moving",
        "fleet status",
    ],
    "GET_TRIP_HISTORY": [
        "Show me MH12AB1234's trip history",
        "Show me the list of trips for Ramesh last week",
        "Show trips yesterday",
        "What journeys did MH14CD5678 make?",
        "Trip history for the Pune van",
        # Regression: found via the all-intent systematic trigger-coverage probe.
        "Trips MH12AB1234 made",
        "Where has MH12AB1234 been today?",
        "Journey history for MH12AB1234",
    ],
    "GET_TRIP_SUMMARY": [
        "How many km did the Mumbai fleet cover last week?",
        "What's the total distance covered this month?",
        "Give me a trip summary for MH12AB1234",
        "How many kilometers driven last week?",
        "What's the distance covered by the fleet yesterday?",
        # Regression: found via the all-intent systematic trigger-coverage probe.
        "How far did MH12AB1234 travel this week?",
        "Total km this week",
    ],
    "GET_ALERT_HISTORY": [
        "Any alerts for MH12AB1234 this month?",
        "Show me the alert history",
        "Give me the list of alerts today",
        "Any alerts this week?",
        "What are the past alerts for the Pune van?",
        # Regression: found via the all-intent systematic trigger-coverage probe — all three
        # fell through to OUT_OF_SCOPE before the fix, including the bare plural noun.
        "What alerts happened today?",
        "Alerts for MH12AB1234 today",
        "alerts",
    ],
    "GET_MAINTENANCE_HISTORY": [
        "When was MH12AB1234 last serviced?",
        "Show me the service history",
        "What's the maintenance history for the truck?",
        "When was the last service done?",
        "When was it last serviced?",
        # Regression: found via the all-intent systematic trigger-coverage probe.
        "Service records for MH12AB1234",
        "Maintenance log for MH12AB1234",
    ],
    "GET_MAINTENANCE_DUE": [
        "Which vehicles are due for service?",
        "Is anything due for maintenance?",
        "What's overdue for maintenance?",
        "Which vehicles need service soon?",
        "Show me the upcoming service list",
        # Regression: found via the all-intent systematic trigger-coverage probe.
        "What needs servicing?",
        "Vehicles that need maintenance",
    ],
    "GET_DRIVER_BEHAVIOR_REPORT": [
        "What's Ramesh's driving score this month?",
        "Show me the driver scorecard",
        "How's the driving behavior for Suresh?",
        "Any harsh events for this driver?",
        "What's the behavior report for Ramesh?",
        # Regression: found via the all-intent systematic trigger-coverage probe.
        "How is Ramesh Kumar driving this month?",
        "Ramesh Kumar's score this month",
    ],
    "GET_FUEL_CONSUMPTION_REPORT": [
        "Fuel efficiency report for the Mumbai fleet",
        "Show me the fuel consumption report",
        "What's the mileage report this month?",
        "Fuel report for MH12AB1234",
        "How's the fuel efficiency this month?",
        # Regression: found via the all-intent systematic trigger-coverage probe — both
        # previously fell through (one to OUT_OF_SCOPE, one misclassified as
        # GET_VEHICLE_FUEL_LEVEL, the exact cross-intent confusion known-gaps.md flagged as a
        # risk before this was fixed).
        "Fuel usage report",
        "How much fuel are we using this month?",
    ],
    "GET_GEOFENCE_LIST": [
        "What geofences apply to MH12AB1234?",
        "List geofences for the Mumbai fleet",
        "Which geofences are set up?",
        "Show me the geofence list",
        "What geofences apply to the Pune van?",
        # Regression: found via the all-intent systematic trigger-coverage probe.
        "What zones apply to MH12AB1234?",
        "geofences",
    ],
    "GET_VEHICLE_ROSTER": [
        "List all my vehicles",
        "Show vehicles in the Pune group",
        "Show me all my vehicles",
        "Give me the fleet roster",
        "What's my vehicle list?",
        # Regression: found via the all-intent systematic trigger-coverage probe — all three
        # fell through to GENERAL_KNOWLEDGE (the "vehicle" DOMAIN_ADJACENT_KEYWORDS fallback)
        # before the fix. Bare "vehicles"/"my vehicles" is the one deliberately-decided
        # ambiguous case in this pass — see known-gaps.md for the reasoning, not just the fix.
        "my vehicles",
        "What vehicles do I have?",
        "vehicles",
    ],
    "GET_DRIVER_ROSTER": [
        "List all drivers",
        "Who drives MH12AB1234?",
        "Show me all drivers",
        "What's the driver list?",
        "Show drivers for the Mumbai fleet",
        # Regression: found via live testing, all fell through to OUT_OF_SCOPE before the fix.
        "Names of drivers",
        "How many drivers do I have?",
        "List of drivers",
        "My drivers",
        "Who are my drivers?",
        # Regression: the motivating gap for the whole all-intent trigger-coverage probe pass —
        # both fell through to OUT_OF_SCOPE before the fix.
        "drivers",
        "which drivers",
    ],
    "CREATE_GEOFENCE": [
        "Create a geofence around our Pune warehouse",
        "Add a geofence for the new site",
        "I want to set up a geofence",
        "Can you draw a geofence on the map?",
        "Make a new geofence for the Mumbai depot",
        # Regression: found via the all-intent systematic trigger-coverage probe — realistic
        # ways to ask that don't use the word "geofence" at all.
        "I need a new zone around the warehouse",
        "Set up a boundary for the depot",
    ],
    "ASSIGN_DRIVER_TO_VEHICLE": [
        "Assign Ramesh to MH12AB1234",
        "Assign a driver to the Pune van",
        "Make him the driver of MH14CD5678",
        "Set the driver for the truck",
        "Please assign her to MH12AB1234",
        # NOT fixed, deliberately: "Put Ramesh on MH12AB1234" / "Ramesh should drive
        # MH12AB1234 now" still fall through (see docs/phase-6-semantic-analysis/
        # known-gaps.md's "left as-is" section) — "put"/"should drive" are too generic to add
        # domain-wide for a backlog/unimplemented intent (mvp=False; the router refuses it
        # regardless of classification), so the false-positive risk elsewhere wasn't judged
        # worth it. No regression case added for those two on purpose.
    ],
    "ACKNOWLEDGE_ALERT": [
        "Acknowledge the speeding alert on MH12AB1234",
        "Mark this alert as resolved",
        "Dismiss the alert for MH12AB1234",
        "Please clear the alert",
        "Acknowledge this alert please",
        # Regression: found via the all-intent systematic trigger-coverage probe.
        "Resolve the speeding alert",
        "I've seen the alert, close it",
    ],
    "SCHEDULE_MAINTENANCE": [
        "Schedule a service for MH12AB1234 next week",
        "Book a service for the truck",
        "Can you arrange a service appointment?",
        "Schedule maintenance for MH14CD5678",
        "I need to schedule a service",
        # Regression: found via the all-intent systematic trigger-coverage probe.
        "Book MH12AB1234 in for a service",
        "Set up an oil change appointment",
    ],
    "EXPLAIN_FEATURE": [
        "How does geofencing work?",
        "What does the driver score mean?",
        "Can you explain how tracking works?",
        "What is geofencing?",
        "How does the alert system work?",
        # Regression: found via the all-intent systematic trigger-coverage probe — the bare
        # gerund/feature-name alone, distinct from GET_GEOFENCE_LIST's bare plural noun (see
        # known-gaps.md for the reasoning).
        "geofencing",
    ],
    "EXPLAIN_ALERT_TYPE": [
        "What counts as harsh braking?",
        "Why did I get a low-fuel alert?",
        "What triggers a speeding alert?",
        "What does the panic alert mean?",
        "What is considered harsh braking?",
    ],
    "APP_FAQ": [
        "How do I add a new vehicle?",
        "How do I register a GPS device?",
        "How do I generate a trip report?",
        "How do I export data as CSV?",
        "How do I add a driver?",
        # Regression: found via the all-intent systematic trigger-coverage probe.
        "Steps to add a new driver",
        "Can I export my data?",
        "faq",
    ],
    "TROUBLESHOOTING_DEVICE": [
        "My GPS device shows offline, what do I do?",
        "The device isn't connecting",
        "GPS is not updating",
        "My device stopped sending data",
        "The GPS isn't working",
        # Regression: found via the all-intent systematic trigger-coverage probe.
        "Device keeps going offline",
        "No signal from the tracker",
    ],
    "POLICY_QUESTION": [
        "How long is trip data retained?",
        "What happens to my data if I cancel?",
        "What's your data retention policy?",
        "How long do you keep alert history?",
        "How long are chat conversations stored?",
        # Regression: found via the all-intent systematic trigger-coverage probe.
        "What's your privacy policy?",
    ],
    "PRICING": [
        "How much does the Pro plan cost?",
        "What's the price of the Enterprise plan?",
        "Is there a discount for 50+ vehicles?",
        "What's the pricing for the Starter plan?",
        "How much is the monthly cost?",
    ],
    "GREETING": ["Hi", "Hello there", "Hey, good morning", "Good afternoon", "Hey", "yo"],
    "GOODBYE": ["Thanks, bye", "That's all for now", "Goodbye", "Thank you, bye", "See you later", "gotta go, thanks"],
    "CHITCHAT": ["How are you?", "What can you do?", "Who are you?", "Tell me a joke", "What's up?", "you're funny", "lol"],
    "ABOUT_TRACK91": [
        "What is Track91?",
        "What does your company do?",
        "Is Track91 a GPS app?",
        "Tell me about Track91",
        "What kind of company is Track91?",
        # Regression: found via the all-intent systematic trigger-coverage probe.
        "who built this",
        "track91",
    ],
    "GENERAL_KNOWLEDGE": [
        "What does AIS-140 mean?",
        "What's the difference between GPS and GLONASS?",
        "What is telematics?",
        "How does GPS triangulation work?",
        "What is an OBD port?",
    ],
    "OUT_OF_SCOPE": [
        "Write me a poem",
        "What's the weather in Delhi?",
        "Tell me about the stock market",
        "What's the capital of France?",
        "Can you recommend a good movie?",
    ],
}


def _cases():
    for intent, phrasings in PARAPHRASES.items():
        assert len(phrasings) >= 5, f"{intent} needs at least 5 paraphrases"
        for phrasing in phrasings:
            yield pytest.param(intent, phrasing, id=f"{intent}::{phrasing[:30]}")


@pytest.mark.parametrize("expected_intent,utterance", list(_cases()))
async def test_paraphrase_classifies_to_expected_intent(expected_intent, utterance):
    classifier = RuleBasedIntentClassifier()
    result = await classifier.classify(utterance)
    assert result == expected_intent


@pytest.mark.parametrize(
    "utterance",
    ["Yes", "Yeah, that one", "No, the other one", "Correct", "That's right"],
)
async def test_affirm_deny_only_fires_when_awaiting_clarification(utterance):
    classifier = RuleBasedIntentClassifier()
    result = await classifier.classify(utterance, session_state={"awaiting_clarification": True})
    assert result == "AFFIRM_DENY"


async def test_affirm_deny_phrase_without_awaiting_clarification_is_not_affirm_deny():
    classifier = RuleBasedIntentClassifier()
    result = await classifier.classify("Yes", session_state={"awaiting_clarification": False})
    assert result != "AFFIRM_DENY"


# EXPLAIN_FEATURE / EXPLAIN_ALERT_TYPE started as fixed phrase/regex matches, which either
# over-matched general-knowledge questions or under-matched realistic rephrasings (both
# failure modes found empirically, not assumed) before being replaced with the
# TRIGGER_COOCCURRENCE mechanism in trigger_patterns.py. These cases pin both directions down.
EXPLAIN_GENERALIZATION_CASES = [
    ("EXPLAIN_FEATURE", "Can you tell me how geofencing works?"),
    ("EXPLAIN_FEATURE", "How does the driver scoring feature work?"),
    ("EXPLAIN_FEATURE", "What's geofencing?"),
    ("EXPLAIN_FEATURE", "Could you explain geofencing to me?"),
    ("EXPLAIN_FEATURE", "I want to understand how tracking works"),
    ("EXPLAIN_FEATURE", "What exactly is geofencing used for?"),
    ("EXPLAIN_ALERT_TYPE", "What does the low fuel alert mean?"),
    ("EXPLAIN_ALERT_TYPE", "Can you explain what the panic alert means?"),
    ("EXPLAIN_ALERT_TYPE", "What does it mean when I get a speeding alert?"),
    ("EXPLAIN_ALERT_TYPE", "What is a device offline alert?"),
    # Must NOT be swallowed by the above — same surface shape, different domain.
    ("GENERAL_KNOWLEDGE", "What does AIS-140 mean?"),
    ("GENERAL_KNOWLEDGE", "How does GPS triangulation work?"),
    ("GENERAL_KNOWLEDGE", "What does telematics mean?"),
    ("GENERAL_KNOWLEDGE", "What's the difference between GPS and GLONASS?"),
]


@pytest.mark.parametrize(
    "expected_intent,utterance",
    [pytest.param(i, u, id=f"{i}::{u[:30]}") for i, u in EXPLAIN_GENERALIZATION_CASES],
)
async def test_explain_feature_and_alert_type_generalize_correctly(expected_intent, utterance):
    classifier = RuleBasedIntentClassifier()
    result = await classifier.classify(utterance)
    assert result == expected_intent


# Regression: found via real testing — "is Track91 a GPS app?" previously either refused
# (OUT_OF_SCOPE) or, worse, fell through to GENERAL_KNOWLEDGE and got a generic "GPS apps in
# general" answer instead of anything about Track91 itself. GENERAL_KNOWLEDGE has zero
# positive triggers of its own (see trigger_patterns.py's module docstring) — it's only ever
# reached once nothing else scores, so any real ABOUT_TRACK91 trigger automatically wins,
# with no separate "priority" mechanism needed.
ABOUT_TRACK91_BEATS_GENERAL_KNOWLEDGE_CASES = [
    "Is Track91 a GPS app?",
    "What is Track91?",
    "What does your company do?",
    "Tell me about Track91",
]


@pytest.mark.parametrize("utterance", ABOUT_TRACK91_BEATS_GENERAL_KNOWLEDGE_CASES)
async def test_about_track91_takes_priority_over_general_knowledge(utterance):
    classifier = RuleBasedIntentClassifier()
    result = await classifier.classify(utterance)
    assert result == "ABOUT_TRACK91"


async def test_general_gps_question_without_track91_still_falls_to_general_knowledge():
    """A question with the same surface shape but no Track91-specific reference must still
    reach GENERAL_KNOWLEDGE — ABOUT_TRACK91's triggers require naming Track91/the platform/the
    company, not just any "what is X" phrasing."""
    classifier = RuleBasedIntentClassifier()
    result = await classifier.classify("What is a GPS tracker?")
    assert result == "GENERAL_KNOWLEDGE"


# Deliberately NOT given a bare-keyword trigger, found during the all-intent systematic
# trigger-coverage probe pass — each of these words genuinely names more than one real intent
# in this taxonomy (not a hypothetical "could be a cut-off question" risk, an actual second
# live candidate), so guessing one would be silently wrong some real fraction of the time. See
# docs/phase-6-semantic-analysis/known-gaps.md's "ambiguous bare keywords" section for the full
# reasoning per word. Pinned here as a real classifier-behavior test, not just documentation, so
# a future change can't silently start guessing without this test catching it and forcing the
# same explicit decision to be made again.
AMBIGUOUS_BARE_KEYWORDS = [
    # GET_TRIP_HISTORY (list past trips) vs GET_TRIP_SUMMARY (aggregate distance/count).
    "trips",
    # GET_MAINTENANCE_HISTORY (past) vs GET_MAINTENANCE_DUE (upcoming) vs SCHEDULE_MAINTENANCE
    # (action) — three real intents share this vocabulary.
    "maintenance",
    "service",
    # GET_VEHICLE_FUEL_LEVEL (one vehicle, right now) vs GET_FUEL_CONSUMPTION_REPORT (fleet,
    # aggregate) — the exact collision known-gaps.md already flagged as a risk.
    "fuel",
    # GET_VEHICLE_IGNITION_STATUS vs GET_FLEET_LIVE_STATUS vs a general vehicle-condition
    # reading (GET_VEHICLE_HEALTH-adjacent) — too vague on its own.
    "status",
    # GET_TRIP_HISTORY vs GET_ALERT_HISTORY vs GET_MAINTENANCE_HISTORY — three intents are
    # literally named "*_HISTORY".
    "history",
    # Singular "alert" (unlike the plural "alerts", which IS given a trigger for
    # GET_ALERT_HISTORY — plural reads as "list them", singular is too tied up with
    # ACKNOWLEDGE_ALERT/EXPLAIN_ALERT_TYPE's own vocabulary to add safely).
    "alert",
]


@pytest.mark.parametrize("utterance", AMBIGUOUS_BARE_KEYWORDS)
async def test_ambiguous_bare_keywords_are_not_silently_guessed(utterance):
    """Must not resolve to any specific real intent — falling through to GENERAL_KNOWLEDGE
    (the DOMAIN_ADJACENT_KEYWORDS fallback) or OUT_OF_SCOPE is the correct, honest behavior for
    a word that genuinely names more than one live intent, until there's a real disambiguation
    mechanism (e.g. asking a clarifying question) worth building for it."""
    classifier = RuleBasedIntentClassifier()
    result = await classifier.classify(utterance)
    assert result in ("GENERAL_KNOWLEDGE", "OUT_OF_SCOPE"), (
        f"{utterance!r} unexpectedly resolved to {result!r} — an ambiguous bare keyword started "
        "being silently guessed; see known-gaps.md before adding a trigger for it"
    )
