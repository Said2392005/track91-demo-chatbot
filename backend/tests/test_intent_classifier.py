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
    ],
    "GET_VEHICLE_SPEED": [
        "How fast is MH12AB1234 going?",
        "What's its speed?",
        "What's the current speed of the truck?",
        "What speed is MH14CD5678 doing right now?",
        "How fast is it going right now?",
    ],
    "GET_VEHICLE_FUEL_LEVEL": [
        "What's the fuel level on MH12AB1234?",
        "How much fuel does it have left?",
        "How much fuel is left in the tank?",
        "Check the gas level for MH14CD5678",
        "How much petrol level is left?",
    ],
    "GET_VEHICLE_HEALTH": [
        "Any engine warnings on MH12AB1234?",
        "Is the vehicle healthy?",
        "Can you run a diagnostic on it?",
        "Is the engine ok?",
        "Any issues with MH14CD5678 right now?",
    ],
    "GET_VEHICLE_IGNITION_STATUS": [
        "Is MH12AB1234 on or off right now?",
        "Is it running right now?",
        "What's the ignition status?",
        "Is the engine on or off?",
        "Is it moving or parked right now?",
    ],
    "GET_FLEET_LIVE_STATUS": [
        "How many vehicles are moving right now?",
        "What's the live status of my fleet?",
        "Give me the current fleet status",
        "How many vehicles are active now?",
        "How many are idle right now?",
    ],
    "GET_TRIP_HISTORY": [
        "Show me MH12AB1234's trip history",
        "Show me the list of trips for Ramesh last week",
        "Show trips yesterday",
        "What journeys did MH14CD5678 make?",
        "Trip history for the Pune van",
    ],
    "GET_TRIP_SUMMARY": [
        "How many km did the Mumbai fleet cover last week?",
        "What's the total distance covered this month?",
        "Give me a trip summary for MH12AB1234",
        "How many kilometers driven last week?",
        "What's the distance covered by the fleet yesterday?",
    ],
    "GET_ALERT_HISTORY": [
        "Any alerts for MH12AB1234 this month?",
        "Show me the alert history",
        "Give me the list of alerts today",
        "Any alerts this week?",
        "What are the past alerts for the Pune van?",
    ],
    "GET_MAINTENANCE_HISTORY": [
        "When was MH12AB1234 last serviced?",
        "Show me the service history",
        "What's the maintenance history for the truck?",
        "When was the last service done?",
        "When was it last serviced?",
    ],
    "GET_MAINTENANCE_DUE": [
        "Which vehicles are due for service?",
        "Is anything due for maintenance?",
        "What's overdue for maintenance?",
        "Which vehicles need service soon?",
        "Show me the upcoming service list",
    ],
    "GET_DRIVER_BEHAVIOR_REPORT": [
        "What's Ramesh's driving score this month?",
        "Show me the driver scorecard",
        "How's the driving behavior for Suresh?",
        "Any harsh events for this driver?",
        "What's the behavior report for Ramesh?",
    ],
    "GET_FUEL_CONSUMPTION_REPORT": [
        "Fuel efficiency report for the Mumbai fleet",
        "Show me the fuel consumption report",
        "What's the mileage report this month?",
        "Fuel report for MH12AB1234",
        "How's the fuel efficiency this month?",
    ],
    "GET_GEOFENCE_LIST": [
        "What geofences apply to MH12AB1234?",
        "List geofences for the Mumbai fleet",
        "Which geofences are set up?",
        "Show me the geofence list",
        "What geofences apply to the Pune van?",
    ],
    "GET_VEHICLE_ROSTER": [
        "List all my vehicles",
        "Show vehicles in the Pune group",
        "Show me all my vehicles",
        "Give me the fleet roster",
        "What's my vehicle list?",
    ],
    "GET_DRIVER_ROSTER": [
        "List all drivers",
        "Who drives MH12AB1234?",
        "Show me all drivers",
        "What's the driver list?",
        "Show drivers for the Mumbai fleet",
    ],
    "CREATE_GEOFENCE": [
        "Create a geofence around our Pune warehouse",
        "Add a geofence for the new site",
        "I want to set up a geofence",
        "Can you draw a geofence on the map?",
        "Make a new geofence for the Mumbai depot",
    ],
    "ASSIGN_DRIVER_TO_VEHICLE": [
        "Assign Ramesh to MH12AB1234",
        "Assign a driver to the Pune van",
        "Make him the driver of MH14CD5678",
        "Set the driver for the truck",
        "Please assign her to MH12AB1234",
    ],
    "ACKNOWLEDGE_ALERT": [
        "Acknowledge the speeding alert on MH12AB1234",
        "Mark this alert as resolved",
        "Dismiss the alert for MH12AB1234",
        "Please clear the alert",
        "Acknowledge this alert please",
    ],
    "SCHEDULE_MAINTENANCE": [
        "Schedule a service for MH12AB1234 next week",
        "Book a service for the truck",
        "Can you arrange a service appointment?",
        "Schedule maintenance for MH14CD5678",
        "I need to schedule a service",
    ],
    "EXPLAIN_FEATURE": [
        "How does geofencing work?",
        "What does the driver score mean?",
        "Can you explain how tracking works?",
        "What is geofencing?",
        "How does the alert system work?",
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
    ],
    "TROUBLESHOOTING_DEVICE": [
        "My GPS device shows offline, what do I do?",
        "The device isn't connecting",
        "GPS is not updating",
        "My device stopped sending data",
        "The GPS isn't working",
    ],
    "POLICY_QUESTION": [
        "How long is trip data retained?",
        "What happens to my data if I cancel?",
        "What's your data retention policy?",
        "How long do you keep alert history?",
        "How long are chat conversations stored?",
    ],
    "PRICING": [
        "How much does the Pro plan cost?",
        "What's the price of the Enterprise plan?",
        "Is there a discount for 50+ vehicles?",
        "What's the pricing for the Starter plan?",
        "How much is the monthly cost?",
    ],
    "GREETING": ["Hi", "Hello there", "Hey, good morning", "Good afternoon", "Hey"],
    "GOODBYE": ["Thanks, bye", "That's all for now", "Goodbye", "Thank you, bye", "See you later"],
    "CHITCHAT": ["How are you?", "What can you do?", "Who are you?", "Tell me a joke", "What's up?"],
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
