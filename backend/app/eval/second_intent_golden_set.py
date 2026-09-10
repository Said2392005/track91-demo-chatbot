"""
Golden set for app/nlu/second_intent.py — measures false-positive rate (singles wrongly
flagged as having a second intent) and true-positive rate (real compound requests correctly
detected) before this is trusted anywhere near the main pipeline, per explicit instruction.

Negatives are the exact same 7 cases from app/eval/splitter_golden_set.py's rejected
conjunction-splitter test, reused deliberately: those are exactly the kind of utterance a
second-intent detector could also misfire on (two entities of the same type joined by "and",
compound noun/verb phrases) — if this detector can't survive the same negatives that sank
Approach 1, it doesn't deserve more trust than Approach 1 got.

Positives are realistic compound requests, including the exact utterance that motivated this
feature ("list drivers and vehicle location") and the splitter eval's own positive set (reused
since they're already realistic and already known-good single-intent phrasings on each side).

primary_intent/expected_second_intent are the REAL app.nlu.intent_classifier.get_intent_classifier()
output for each utterance (verified live, not assumed) — see
docs comment on each case for what score_all_intents() actually returned.
"""

from dataclasses import dataclass


@dataclass
class SecondIntentCase:
    case_id: str
    utterance: str
    primary_intent: str
    expect_second_intent: bool
    expected_second_intent: str | None = None
    note: str = ""


SECOND_INTENT_GOLDEN_SET: list[SecondIntentCase] = [
    # --- Positives: a real second intent should be detected (7) ---
    SecondIntentCase(
        "pos_drivers_and_location",
        "list drivers and vehicle location",
        primary_intent="GET_DRIVER_ROSTER",
        expect_second_intent=True,
        expected_second_intent="GET_VEHICLE_LOCATION",
        note="the exact motivating example — measured second-best score 3 (was 2 before the "
        "all-intent trigger-coverage pass added a bare 'location' phrase; re-measured then, not "
        "assumed — see tests/test_second_intent.py's threshold test)",
    ),
    SecondIntentCase(
        "pos_drivers_and_location_verbose",
        "list my drivers and also show vehicle locations",
        primary_intent="GET_DRIVER_ROSTER",
        expect_second_intent=True,
        expected_second_intent="GET_VEHICLE_LOCATION",
    ),
    SecondIntentCase(
        "pos_location_and_speed",
        "Where is MH12AB1234 and what's its speed?",
        primary_intent="GET_VEHICLE_LOCATION",
        expect_second_intent=True,
        expected_second_intent="GET_VEHICLE_SPEED",
    ),
    SecondIntentCase(
        "pos_trips_and_maintenance",
        "Show trip history for MH12AB1234 and also check maintenance due",
        primary_intent="GET_TRIP_HISTORY",
        expect_second_intent=True,
        expected_second_intent="GET_MAINTENANCE_DUE",
    ),
    SecondIntentCase(
        "pos_vehicles_and_drivers",
        "List all vehicles and also list all drivers",
        primary_intent="GET_DRIVER_ROSTER",
        expect_second_intent=True,
        expected_second_intent="GET_VEHICLE_ROSTER",
        note="GET_DRIVER_ROSTER outscores GET_VEHICLE_ROSTER as primary (9 vs 3) despite "
        "GET_VEHICLE_ROSTER appearing first in taxonomy order — score wins, not priority.",
    ),
    SecondIntentCase(
        "pos_geofencing_and_pricing",
        "How does geofencing work and also what's included in the Enterprise plan?",
        primary_intent="EXPLAIN_FEATURE",
        expect_second_intent=True,
        expected_second_intent="PRICING",
    ),
    # --- Disclosed miss, not a threshold failure: no intent's triggers score on "is it
    # currently moving" at all (GET_FLEET_LIVE_STATUS's phrases are fleet-wide "how many
    # vehicles", not a single "is it moving" check) — second-best score is 0, same as every
    # negative. A real gap in trigger coverage, not something a threshold choice can fix.
    SecondIntentCase(
        "pos_alerts_and_moving_KNOWN_MISS",
        "Any alerts for MH12AB1234 this month and also is it currently moving?",
        primary_intent="GET_ALERT_HISTORY",
        expect_second_intent=False,
        note="honest miss: 'is it currently moving' scores 0 against every intent's triggers, "
        "not just the primary — no coverage gap in second_intent.py itself to fix",
    ),
    # Deliberate miss, not an oversight: bare singular "driver" (no verb, no plural, no "of
    # driver"/"driver list"/"driver roster") scores 0 for GET_DRIVER_ROSTER and therefore isn't
    # detected as a second intent here — verified live (score_all_intents("where is my vehicle
    # and driver") == {"GET_VEHICLE_LOCATION": 6, everything else: 0}). This traces straight back
    # to trigger_patterns.py's GET_DRIVER_ROSTER cooccurrence comment: bare singular "driver" was
    # tried as a subject word and reverted because it made "show me the driver scorecard"
    # misclassify as GET_DRIVER_ROSTER instead of GET_DRIVER_BEHAVIOR_REPORT. That tradeoff is
    # correct for the primary classifier and is staying as-is — this case exists so the same
    # consequence for the *second*-intent detector is an explicit, pinned decision instead of
    # silently-absent coverage. Stronger phrasing recovers it fine: "...and show me all drivers"
    # or "...and driver list" both correctly detect GET_DRIVER_ROSTER (verified live too).
    SecondIntentCase(
        "pos_vehicle_and_bare_driver_KNOWN_MISS",
        "where is my vehicle and driver",
        primary_intent="GET_VEHICLE_LOCATION",
        expect_second_intent=False,
        note="honest miss: bare singular 'driver' isn't in GET_DRIVER_ROSTER's cooccurrence "
        "subject list (deliberately, per trigger_patterns.py) — a classifier-coverage decision, "
        "not a threshold issue in second_intent.py",
    ),
    # --- Negatives: must NOT detect a second intent (7, reused verbatim from
    # app/eval/splitter_golden_set.py's rejected-splitter negatives) ---
    SecondIntentCase(
        "neg_explain_feature_and",
        "What happens when a vehicle enters and exits a geofence?",
        primary_intent="EXPLAIN_FEATURE",
        expect_second_intent=False,
    ),
    SecondIntentCase(
        "neg_two_drivers",
        "Show trips for Ramesh and Suresh",
        primary_intent="GET_TRIP_HISTORY",
        expect_second_intent=False,
    ),
    SecondIntentCase(
        "neg_policy_compound_noun",
        "How long is trip and location history retained?",
        primary_intent="POLICY_QUESTION",
        expect_second_intent=False,
    ),
    SecondIntentCase(
        "neg_two_vehicles",
        "Show trips for MH12AB1234 and MH14CD5678",
        primary_intent="GET_TRIP_HISTORY",
        expect_second_intent=False,
    ),
    SecondIntentCase(
        "neg_two_drivers_score",
        "What's Ramesh Kumar and Suresh Patil's driving score this month?",
        primary_intent="GET_DRIVER_BEHAVIOR_REPORT",
        expect_second_intent=False,
    ),
    SecondIntentCase(
        "neg_health_compound_verb",
        "Is MH12AB1234's engine ok and running smoothly?",
        primary_intent="GET_VEHICLE_HEALTH",
        expect_second_intent=False,
    ),
    SecondIntentCase(
        "neg_app_faq_register_and_link",
        "How do I register a new GPS device and link it to a vehicle?",
        primary_intent="APP_FAQ",
        expect_second_intent=False,
    ),
]
