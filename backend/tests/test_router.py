"""
Deterministic router tests — Phase 9 testing requirement (roadmap.md): table-driven,
(intent, entities, memory-state) -> (tool called, params passed). Pure and synchronous — no
Mongo, no LLM, no I/O — router.route() takes already-classified intent/entities as input.
"""

import pytest
from bson import ObjectId

from app.router.router import route

VEHICLE_ID = ObjectId()
DRIVER_ID = ObjectId()
DATE_RANGE = ("2026-07-01", "2026-07-28")  # opaque to the router; it never inspects the value

ROUTER_TABLE = [
    pytest.param(
        "GET_VEHICLE_SPEED",
        {"vehicle_id": VEHICLE_ID},
        None,
        "TOOL_CALL",
        "get_vehicle_speed",
        "LIVE_API",
        {"vehicle_id": VEHICLE_ID},
        id="live_gps_intent",
    ),
    pytest.param(
        "GET_TRIP_HISTORY",
        {"vehicle_id": VEHICLE_ID, "date_range": DATE_RANGE},
        None,
        "TOOL_CALL",
        "get_trip_history",
        "MONGO_REPO",
        {"vehicle_id": VEHICLE_ID, "date_range": DATE_RANGE},
        id="mongo_history_intent",
    ),
    pytest.param(
        "EXPLAIN_FEATURE",
        {"kb_topic": "How does geofencing work?"},
        None,
        "TOOL_CALL",
        "explain_feature",
        "RAG",
        {"kb_topic": "How does geofencing work?"},
        id="rag_kb_intent",
    ),
    pytest.param(
        "PRICING",
        {"kb_topic": "How much does the Pro plan cost?"},
        None,
        "TOOL_CALL",
        "pricing",
        "RAG",
        {"kb_topic": "How much does the Pro plan cost?"},
        id="pricing_intent_routes_to_rag_never_bare_llm",
    ),
    pytest.param(
        "GENERAL_KNOWLEDGE",
        {"kb_topic": "What does AIS-140 mean?"},
        None,
        "TOOL_CALL",
        "general_knowledge",
        "GENERAL_FALLBACK",
        {"kb_topic": "What does AIS-140 mean?"},
        id="general_knowledge_fallback",
    ),
    pytest.param(
        "GET_VEHICLE_SPEED",
        {},
        None,
        "CLARIFICATION_NEEDED",
        None,
        None,
        {},
        id="missing_required_entity_produces_clarification_not_tool_call",
    ),
    pytest.param(
        "GET_VEHICLE_SPEED",
        {},
        {"active_entities": {"vehicle_id": VEHICLE_ID}},
        "TOOL_CALL",
        "get_vehicle_speed",
        "LIVE_API",
        {"vehicle_id": VEHICLE_ID},
        id="memory_state_fills_in_missing_entity",
    ),
    pytest.param(
        "GET_TRIP_HISTORY",
        {"driver_id": DRIVER_ID, "date_range": DATE_RANGE},
        None,
        "TOOL_CALL",
        "get_trip_history",
        "MONGO_REPO",
        {"driver_id": DRIVER_ID, "date_range": DATE_RANGE},
        id="required_one_of_satisfied_by_driver_alone",
    ),
    pytest.param(
        "GET_TRIP_HISTORY",
        {"date_range": DATE_RANGE},
        None,
        "CLARIFICATION_NEEDED",
        None,
        None,
        {},
        id="required_one_of_unmet_produces_clarification",
    ),
    pytest.param(
        "CREATE_GEOFENCE",
        {"location_ref": "Pune Warehouse"},
        None,
        "BACKLOG_UNSUPPORTED",
        None,
        None,
        {},
        id="backlog_intent_is_not_a_tool_call",
    ),
    pytest.param(
        "GREETING",
        {},
        None,
        "NO_TOOL",
        None,
        None,
        {},
        id="meta_intent_needs_no_tool",
    ),
    pytest.param(
        "NOT_A_REAL_INTENT",
        {},
        None,
        "UNKNOWN_INTENT",
        None,
        None,
        {},
        id="unknown_intent_label",
    ),
]


@pytest.mark.parametrize(
    "intent,entities,memory_state,expected_outcome,expected_tool,expected_subsystem,expected_params",
    ROUTER_TABLE,
)
def test_route_table(intent, entities, memory_state, expected_outcome, expected_tool, expected_subsystem, expected_params):
    decision = route(intent, entities, memory_state)

    assert decision.outcome == expected_outcome
    assert decision.tool_name == expected_tool
    assert decision.subsystem == expected_subsystem
    if expected_outcome == "TOOL_CALL":
        for k, v in expected_params.items():
            assert decision.params[k] == v


def test_missing_entity_produces_a_clarifying_question_string():
    decision = route("GET_VEHICLE_SPEED", {}, None)
    assert decision.outcome == "CLARIFICATION_NEEDED"
    assert decision.clarifying_question
    assert "vehicle" in decision.clarifying_question.lower()


def test_missing_entity_decision_records_which_requirement_is_missing():
    """missing_entity is what clarify_node persists as pending_clarification so the next turn
    can complete this intent directly instead of re-classifying from scratch."""
    decision = route("GET_VEHICLE_SPEED", {}, None)
    assert decision.missing_entity == "vehicle_ref"

    decision = route("GET_TRIP_HISTORY", {}, None)
    assert decision.missing_entity == "date_range"  # required= is checked before required_one_of=

    decision = route("GET_VEHICLE_SPEED", {"vehicle_id": VEHICLE_ID}, None)
    assert decision.outcome == "TOOL_CALL"
    assert decision.missing_entity is None


def test_pricing_tool_is_the_gated_rag_handler_not_a_bare_llm_call():
    """Confirms at the registry level (not just by convention) that PRICING's handler is
    app.tools.kb_tools.pricing — which hardcodes category="pricing" into answer_kb_query(), the
    gated pipeline — never app.tools.general_knowledge.general_knowledge or any other handler
    that would call the LLM directly."""
    from app.router.registry import TOOL_REGISTRY
    from app.tools import kb_tools

    assert TOOL_REGISTRY["PRICING"].handler is kb_tools.pricing
    assert TOOL_REGISTRY["PRICING"].subsystem == "RAG"


def test_memory_state_does_not_override_an_explicit_entity_in_this_message():
    other_vehicle = ObjectId()
    decision = route(
        "GET_VEHICLE_SPEED",
        {"vehicle_id": VEHICLE_ID},
        {"active_entities": {"vehicle_id": other_vehicle}},
    )
    assert decision.params["vehicle_id"] == VEHICLE_ID
