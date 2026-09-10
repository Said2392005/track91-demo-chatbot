"""
AI eval golden set — Phase 12 requirement: 40-60 Q&A pairs across every intent, scored on
intent-classification accuracy, entity-extraction accuracy, retrieval precision, and answer
faithfulness (app/eval/scorer.py, app/eval/runner.py).

Entity expectations are symbolic, not literal ObjectIds — `"plate:MH12AB1234"` /
`"driver:Ramesh Kumar"` are resolved against known seeded fixtures at eval time
(app/eval/runner.py's seed_eval_fixtures()), and `"PRESENT"` means "must be non-empty, value
not checked" (used for date_range and kb_topic, which are free-form).

`expected_final_intent` defaults to `expected_raw_intent` when not given — they only diverge
for the two CLARIFICATION_NEEDED cases (classifier output vs. the pipeline's own downstream
decision once entity resolution fails) and, trivially, don't apply to AFFIRM_DENY (a
NONE-subsystem intent with no entity-resolution step to diverge through).
"""

from dataclasses import dataclass, field


@dataclass
class GoldenCase:
    case_id: str
    utterance: str
    expected_raw_intent: str
    expected_final_intent: str | None = None  # defaults to expected_raw_intent
    expected_entities: dict[str, str] = field(default_factory=dict)
    kb_category: str | None = None  # set only for RAG-answerable cases with real KB content
    relevant_doc_ids: list[str] = field(default_factory=list)
    require_approved_only: bool = False  # PRICING gate: every citation must be approved
    session_state: dict | None = None
    notes: str = ""

    def __post_init__(self):
        if self.expected_final_intent is None:
            self.expected_final_intent = self.expected_raw_intent


GOLDEN_SET: list[GoldenCase] = [
    # --- A. LIVE_API (7) ---
    GoldenCase("live_location", "Where is MH12AB1234 right now?", "GET_VEHICLE_LOCATION", expected_entities={"vehicle_id": "plate:MH12AB1234"}),
    GoldenCase("live_speed", "How fast is MH12AB1234 going?", "GET_VEHICLE_SPEED", expected_entities={"vehicle_id": "plate:MH12AB1234"}),
    GoldenCase("live_fuel", "What's the fuel level on MH12AB1234?", "GET_VEHICLE_FUEL_LEVEL", expected_entities={"vehicle_id": "plate:MH12AB1234"}),
    GoldenCase("live_health", "Any engine warnings on MH12AB1234?", "GET_VEHICLE_HEALTH", expected_entities={"vehicle_id": "plate:MH12AB1234"}),
    GoldenCase("live_ignition", "Is MH12AB1234 on or off right now?", "GET_VEHICLE_IGNITION_STATUS", expected_entities={"vehicle_id": "plate:MH12AB1234"}),
    GoldenCase("live_fleet_status", "How many vehicles are moving right now?", "GET_FLEET_LIVE_STATUS"),
    # Added via the all-intent systematic trigger-coverage probe pass (see
    # docs/phase-6-semantic-analysis/known-gaps.md) — end-to-end proof that a bare-keyword
    # phrasing resolves through the full pipeline (classify + entity extraction + routing), not
    # just at the classifier level (already covered separately in test_intent_classifier.py).
    GoldenCase("bare_fleet_status", "fleet status", "GET_FLEET_LIVE_STATUS", notes="bare-keyword regression case for the all-intent trigger-coverage pass"),
    # --- B. MONGO_REPO (14) ---
    GoldenCase("trip_history_vehicle", "Show me MH12AB1234's trip history yesterday", "GET_TRIP_HISTORY", expected_entities={"vehicle_id": "plate:MH12AB1234", "date_range": "PRESENT"}),
    GoldenCase("trip_history_driver", "Show trips for Ramesh Kumar yesterday", "GET_TRIP_HISTORY", expected_entities={"driver_id": "driver:Ramesh Kumar", "date_range": "PRESENT"}),
    GoldenCase("trip_summary", "How many km did MH12AB1234 cover last week?", "GET_TRIP_SUMMARY", expected_entities={"date_range": "PRESENT"}),
    GoldenCase("alert_history", "Any alerts for MH12AB1234 this month?", "GET_ALERT_HISTORY", expected_entities={"date_range": "PRESENT"}),
    GoldenCase(
        "bare_alert_history",
        "alerts",
        "GET_ALERT_HISTORY",
        expected_final_intent="CLARIFICATION_NEEDED",
        notes=(
            "bare-keyword regression case for the all-intent trigger-coverage pass — raw_intent "
            "correctly resolves from the bare keyword alone; final_intent still correctly "
            "downgrades to CLARIFICATION_NEEDED since date_range (required) isn't in a single "
            "bare noun, same as the pre-existing clarification_missing_date case below"
        ),
    ),
    GoldenCase("maintenance_history", "When was MH12AB1234 last serviced?", "GET_MAINTENANCE_HISTORY", expected_entities={"vehicle_id": "plate:MH12AB1234"}),
    GoldenCase("maintenance_due", "Which vehicles are due for service?", "GET_MAINTENANCE_DUE"),
    GoldenCase("driver_behavior", "What's Ramesh Kumar's driving score this month?", "GET_DRIVER_BEHAVIOR_REPORT", expected_entities={"driver_id": "driver:Ramesh Kumar", "date_range": "PRESENT"}),
    GoldenCase("fuel_report", "Fuel efficiency report for last month", "GET_FUEL_CONSUMPTION_REPORT", expected_entities={"date_range": "PRESENT"}),
    GoldenCase("geofence_list", "What geofences apply to MH12AB1234?", "GET_GEOFENCE_LIST"),
    GoldenCase("bare_geofence_list", "geofences", "GET_GEOFENCE_LIST", notes="bare-keyword regression case for the all-intent trigger-coverage pass"),
    GoldenCase("vehicle_roster", "List all my vehicles", "GET_VEHICLE_ROSTER"),
    GoldenCase("bare_vehicle_roster", "vehicles", "GET_VEHICLE_ROSTER", notes="bare-keyword regression case for the all-intent trigger-coverage pass — the one deliberately-decided ambiguous-adjacent case, see known-gaps.md"),
    GoldenCase("driver_roster", "List all drivers", "GET_DRIVER_ROSTER"),
    # The motivating gap for this whole pass — see the conversation history / known-gaps.md.
    GoldenCase("bare_driver_roster", "drivers", "GET_DRIVER_ROSTER", notes="bare-keyword regression case for the all-intent trigger-coverage pass"),
    # --- C. Backlog (4) — intent classification only; router rejects these (Phase 9) ---
    # CREATE_GEOFENCE and SCHEDULE_MAINTENANCE's final_intent legitimately downgrades to
    # CLARIFICATION_NEEDED, not a bug: entity_extractor.py never implements free-text
    # location_ref extraction (documented as out of scope while CREATE_GEOFENCE stays backlog),
    # and date_parser.py doesn't recognize "next week" (only explicit ranges and a fixed set of
    # relative phrases) — so their required entities are legitimately never resolved. Getting
    # this wrong in the golden set itself, not the classifier, was the actual first-run finding.
    GoldenCase(
        "backlog_create_geofence",
        "Create a geofence around our Pune warehouse",
        "CREATE_GEOFENCE",
        expected_final_intent="CLARIFICATION_NEEDED",
        notes="location_ref extraction is unimplemented while this intent stays backlog",
    ),
    GoldenCase(
        "backlog_assign_driver",
        "Assign Ramesh Kumar to MH12AB1234",
        "ASSIGN_DRIVER_TO_VEHICLE",
        expected_final_intent="CLARIFICATION_NEEDED",
        notes=(
            "driver_ref extraction's proper-noun regex greedily pairs the sentence-initial "
            'capitalized verb "Assign" with the following capitalized word ("Ramesh"), '
            'producing candidates ["Assign Ramesh", "Kumar"] — neither resolves to the driver. '
            "A real Phase 6 gap surfaced by this golden set, not fixed here since "
            "ASSIGN_DRIVER_TO_VEHICLE stays backlog/unimplemented regardless."
        ),
    ),
    GoldenCase("backlog_ack_alert", "Acknowledge the speeding alert on MH12AB1234", "ACKNOWLEDGE_ALERT"),
    GoldenCase(
        "backlog_schedule_maintenance",
        "Schedule a service for MH12AB1234 next week",
        "SCHEDULE_MAINTENANCE",
        expected_final_intent="CLARIFICATION_NEEDED",
        notes="date_parser.py doesn't recognize \"next week\"",
    ),
    # --- D. RAG (15) ---
    GoldenCase("explain_feature_1", "How does geofencing work?", "EXPLAIN_FEATURE", kb_category="feature_guide", relevant_doc_ids=["geofencing-feature-guide"]),
    GoldenCase("explain_feature_2", "What happens when a vehicle enters or exits a geofence?", "EXPLAIN_FEATURE", kb_category="feature_guide", relevant_doc_ids=["geofencing-feature-guide"]),
    # EXPLAIN_ALERT_TYPE: intent-classification only, no kb_category — this synthetic KB has no
    # dedicated alert-type glossary doc (Phase 4 never authored one), so there's no ground truth
    # to score retrieval/groundedness against. A real content gap, not a metric fudged to pass.
    GoldenCase("explain_alert_type_1", "What does the low fuel alert mean?", "EXPLAIN_ALERT_TYPE", notes="no dedicated KB doc — intent-only"),
    GoldenCase("explain_alert_type_2", "Why did I get a harsh braking alert?", "EXPLAIN_ALERT_TYPE", notes="no dedicated KB doc — intent-only"),
    GoldenCase("app_faq_1", "How do I register a new GPS device?", "APP_FAQ", kb_category="app_faq", relevant_doc_ids=["track91-app-faq"]),
    GoldenCase("app_faq_2", "How do I add a driver to my fleet?", "APP_FAQ", kb_category="app_faq", relevant_doc_ids=["track91-app-faq"]),
    GoldenCase("troubleshooting_1", "My GPS device shows offline, what should I do?", "TROUBLESHOOTING_DEVICE", kb_category="troubleshooting", relevant_doc_ids=["gps-device-offline-troubleshooting"]),
    GoldenCase("troubleshooting_2", "Why would a GPS device stop sending data?", "TROUBLESHOOTING_DEVICE", kb_category="troubleshooting", relevant_doc_ids=["gps-device-offline-troubleshooting"]),
    GoldenCase("policy_1", "How long is trip and location history retained?", "POLICY_QUESTION", kb_category="policy", relevant_doc_ids=["data-retention-policy"]),
    GoldenCase("policy_2", "What happens to my data if I cancel my subscription?", "POLICY_QUESTION", kb_category="policy", relevant_doc_ids=["data-retention-policy"]),
    GoldenCase("pricing_approved_1", "How much does the Pro plan cost per month?", "PRICING", kb_category="pricing", relevant_doc_ids=["track91-pricing-sheet"], require_approved_only=True),
    GoldenCase("pricing_approved_2", "What's included in the Enterprise plan?", "PRICING", kb_category="pricing", relevant_doc_ids=["track91-pricing-sheet"], require_approved_only=True),
    GoldenCase(
        "pricing_ambiguous",
        "What is your custom pricing rate for 1000 or more vehicles?",
        "PRICING",
        kb_category="pricing",
        relevant_doc_ids=["track91-pricing-sheet", "enterprise-pricing-draft-notes"],
        require_approved_only=True,
        notes="the unapproved draft doc ranks #1 by raw distance (Phase 7 finding) — groundedness check proves the gate still holds",
    ),
    GoldenCase("general_knowledge_1", "What does AIS-140 mean?", "GENERAL_KNOWLEDGE", notes="never backed by the KB by design — intent-only"),
    GoldenCase("general_knowledge_2", "How does GPS triangulation work?", "GENERAL_KNOWLEDGE", notes="never backed by the KB by design — intent-only"),
    # --- E. Meta (9) ---
    GoldenCase("greeting", "Hi there", "GREETING"),
    GoldenCase("goodbye", "Thanks, bye", "GOODBYE"),
    GoldenCase("chitchat", "What can you do?", "CHITCHAT"),
    GoldenCase(
        "about_track91",
        "Is Track91 a GPS app?",
        "ABOUT_TRACK91",
        notes="added after real testing showed this fell to OUT_OF_SCOPE, or worse GENERAL_KNOWLEDGE's generic GPS-apps answer",
    ),
    GoldenCase("out_of_scope", "Write me a poem", "OUT_OF_SCOPE"),
    GoldenCase(
        "clarification_pronoun_no_context",
        "What's its speed?",
        "GET_VEHICLE_SPEED",
        expected_final_intent="CLARIFICATION_NEEDED",
        session_state={},
        notes="raw classifier intent is GET_VEHICLE_SPEED; the pipeline downgrades to CLARIFICATION_NEEDED once coreference has nothing to resolve against",
    ),
    GoldenCase(
        "clarification_missing_date",
        "Show trips",
        "GET_TRIP_HISTORY",
        expected_final_intent="CLARIFICATION_NEEDED",
        session_state={},
        notes="no vehicle/driver and no date_range at all",
    ),
    # session_state needs BOTH keys — found stale while investigating an unrelated token-usage
    # change. app/eval/runner.py's _run_case() exercises the classifier two different ways:
    # raw_intent via a direct classifier.classify(utterance, case.session_state) call (reads
    # the literal "awaiting_clarification" key), and final_intent via
    # app.nlu.pipeline.analyze(), which now derives its OWN "awaiting_clarification" from
    # "pending_clarification" (added for the pending-clarification-resume feature) and
    # overrides whatever raw flag was passed. A session_state with only one of the two keys
    # satisfies exactly one of runner.py's two call paths and silently fails the other — not a
    # real product bug (production only ever reaches analyze() through
    # app/agent/nodes.py's semantic_analysis_node, which already passes pending_clarification,
    # never a raw flag directly), just a test fixture that predated the feature it's now
    # inconsistent with.
    GoldenCase(
        "affirm_deny_yes",
        "Yes",
        "AFFIRM_DENY",
        session_state={
            "awaiting_clarification": True,
            "pending_clarification": {"intent": "GET_VEHICLE_LOCATION", "missing": "vehicle_ref"},
        },
    ),
    GoldenCase(
        "affirm_deny_no",
        "No, the other one",
        "AFFIRM_DENY",
        session_state={
            "awaiting_clarification": True,
            "pending_clarification": {"intent": "GET_VEHICLE_LOCATION", "missing": "vehicle_ref"},
        },
    ),
]
