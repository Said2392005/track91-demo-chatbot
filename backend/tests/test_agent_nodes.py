"""
Node-level unit tests — Phase 10 testing requirement. Each node tested in isolation against
real dependencies (Mongo, mock GPS, fake LLM) but without the full graph. Special attention to
the property that motivated app/agent/serialization.py: no bson.ObjectId anywhere in a node's
returned state update, since LangGraph's checkpoint serializer cannot handle it (verified
empirically before writing any node code — see serialization.py's docstring).
"""

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.agent import nodes
from app.db.repositories.session_repository import SessionRepository
from app.llm.providers.fake import FakeLLMProvider
from app.nlu.intent_classifier import RuleBasedIntentClassifier
from app.tools.fleet_gps_client import MockFleetGPSClient


def _assert_no_object_id(value):
    if isinstance(value, ObjectId):
        pytest.fail(f"found a raw ObjectId in state: {value!r}")
    if isinstance(value, dict):
        for v in value.values():
            _assert_no_object_id(v)
    if isinstance(value, list):
        for v in value:
            _assert_no_object_id(v)


async def test_entry_node_returns_string_active_entities_not_objectid(db):
    session_repo = SessionRepository(db)
    company_id, user_id, vehicle_id = ObjectId(), ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)
    session = await session_repo.create(company_id, user_id, now)
    await session_repo.set_active_entity(company_id, session["_id"], "vehicle", vehicle_id, now)

    entry_node = nodes.make_entry_node(session_repo)
    result = await entry_node(
        {"company_id": str(company_id), "session_id": str(session["_id"]), "now": now}
    )

    _assert_no_object_id(result)
    assert result["active_entities"]["vehicle_id"] == str(vehicle_id)


async def test_entry_node_no_active_entities_returns_empty(db):
    session_repo = SessionRepository(db)
    company_id, user_id = ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)
    session = await session_repo.create(company_id, user_id, now)

    entry_node = nodes.make_entry_node(session_repo)
    result = await entry_node({"company_id": str(company_id), "session_id": str(session["_id"]), "now": now})

    assert result["active_entities"] == {}


async def test_semantic_analysis_node_resolves_explicit_plate(db):
    company_id, vehicle_id = ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)
    await db.vehicles.insert_one(
        {"_id": vehicle_id, "company_id": company_id, "plate_number": "MH12AB1234", "status": "active", "created_at": now}
    )

    node = nodes.make_semantic_analysis_node(RuleBasedIntentClassifier(), db)
    result = await node({"utterance": "Where is MH12AB1234?", "company_id": str(company_id), "active_entities": {}, "now": now})

    assert result["final_intent"] == "GET_VEHICLE_LOCATION"
    assert result["entities"]["vehicle_id"] == str(vehicle_id)
    _assert_no_object_id(result)


def test_route_condition_maps_every_outcome():
    assert nodes.route_condition({"route_outcome": "CLARIFICATION_NEEDED"}) == "clarify"
    assert nodes.route_condition({"route_outcome": "TOOL_CALL", "subsystem": "LIVE_API"}) == "gps_tool"
    assert nodes.route_condition({"route_outcome": "TOOL_CALL", "subsystem": "MONGO_REPO"}) == "mongo_tool"
    assert nodes.route_condition({"route_outcome": "TOOL_CALL", "subsystem": "RAG"}) == "rag_tool"
    assert nodes.route_condition({"route_outcome": "TOOL_CALL", "subsystem": "GENERAL_FALLBACK"}) == "rag_tool"
    assert nodes.route_condition({"route_outcome": "NO_TOOL"}) == "synthesis"
    assert nodes.route_condition({"route_outcome": "BACKLOG_UNSUPPORTED"}) == "synthesis"
    assert nodes.route_condition({"route_outcome": "UNKNOWN_INTENT"}) == "synthesis"


async def test_router_node_produces_tool_call_for_live_api_intent():
    router_node = nodes.make_router_node()
    vehicle_id_str = str(ObjectId())
    result = await router_node(
        {"raw_intent": "GET_VEHICLE_SPEED", "final_intent": "GET_VEHICLE_SPEED", "entities": {"vehicle_id": vehicle_id_str}, "active_entities": {}}
    )
    assert result["route_outcome"] == "TOOL_CALL"
    assert result["subsystem"] == "LIVE_API"


async def test_router_node_routes_on_raw_intent_not_downgraded_final_intent():
    """Phase 6's pipeline.analyze() may already downgrade final_intent to
    CLARIFICATION_NEEDED when entities are unresolved — router_node must still route on
    raw_intent so Phase 9's route() makes its own (superset) determination, including its
    memory_state fallback. Regression test for the bug caught in
    tests/test_agent_graph_integration.py's active-entity-expiry scenario."""
    router_node = nodes.make_router_node()
    result = await router_node(
        {"raw_intent": "GET_VEHICLE_SPEED", "final_intent": "CLARIFICATION_NEEDED", "entities": {}, "active_entities": {}}
    )
    assert result["route_outcome"] == "CLARIFICATION_NEEDED"
    assert result["clarifying_question"]


async def test_clarify_node_returns_clarifying_question_as_response():
    clarify_node = nodes.make_clarify_node()
    result = await clarify_node({"clarifying_question": "Which vehicle are you asking about?"})
    assert result["response_text"] == "Which vehicle are you asking about?"


async def test_gps_tool_node_returns_checkpoint_safe_data():
    vehicle_id = ObjectId()
    node = nodes.make_gps_tool_node(MockFleetGPSClient())
    state = {
        "route_outcome": "TOOL_CALL",
        "final_intent": "GET_VEHICLE_SPEED",
        "tool_name": "get_vehicle_speed",
        "subsystem": "LIVE_API",
        "route_params": {"vehicle_id": str(vehicle_id)},
        "clarifying_question": None,
        "now": datetime.now(timezone.utc),
    }
    result = await node(state)
    _assert_no_object_id(result)
    assert "speed_kmph" in result["tool_result"]


async def test_mongo_tool_node_sanitizes_raw_mongo_documents(db):
    company_id, vehicle_id = ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)
    await db.trips.insert_one(
        {"company_id": company_id, "vehicle_id": vehicle_id, "start_time": now, "end_time": now, "distance_km": 5.0, "created_at": now}
    )

    node = nodes.make_mongo_tool_node(db)
    state = {
        "route_outcome": "TOOL_CALL",
        "final_intent": "GET_TRIP_HISTORY",
        "tool_name": "get_trip_history",
        "subsystem": "MONGO_REPO",
        "route_params": {
            "vehicle_id": str(vehicle_id),
            "date_range": (datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2027, 1, 1, tzinfo=timezone.utc)),
        },
        "clarifying_question": None,
        "company_id": str(company_id),
        "now": now,
    }
    result = await node(state)

    _assert_no_object_id(result)  # this is the property that matters most here
    assert len(result["tool_result"]) == 1
    assert result["tool_result"][0]["distance_km"] == 5.0
    assert isinstance(result["tool_result"][0]["_id"], str)


async def test_rag_tool_node_returns_plain_dict_not_dataclass():
    from app.kb.chunker import chunk_document, parse_source_file
    from app.kb.ingest import ingest_chunks
    import chromadb

    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection("kb_chunks_node_test")
    doc = parse_source_file(
        __import__("pathlib").Path(__file__).resolve().parent.parent / "kb_sources" / "feature_guide" / "geofencing-feature-guide.md"
    )
    ingest_chunks(chunk_document(doc), collection=collection)

    fake = FakeLLMProvider(canned_response="Geofencing explanation. [Source 1]")
    node = nodes.make_rag_tool_node(fake, collection)
    state = {
        "route_outcome": "TOOL_CALL",
        "final_intent": "EXPLAIN_FEATURE",
        "tool_name": "explain_feature",
        "subsystem": "RAG",
        "route_params": {"kb_topic": "How does geofencing work?"},
        "clarifying_question": None,
    }
    result = await node(state)

    assert isinstance(result["tool_result"], dict)
    assert result["tool_result"]["answer"] == "Geofencing explanation. [Source 1]"


async def test_synthesis_node_passes_through_clarification_response():
    synthesis_node = nodes.make_synthesis_node(FakeLLMProvider())
    result = await synthesis_node({"route_outcome": "CLARIFICATION_NEEDED"})
    assert result == {}, "must not overwrite response_text already set by clarify_node"


async def test_synthesis_node_uses_template_for_meta_intent():
    synthesis_node = nodes.make_synthesis_node(FakeLLMProvider())
    result = await synthesis_node({"route_outcome": "NO_TOOL", "final_intent": "GREETING"})
    assert "help" in result["response_text"].lower()


async def test_synthesis_node_uses_rag_answer_directly_without_extra_llm_call():
    fake = FakeLLMProvider(canned_response="should not be used")
    synthesis_node = nodes.make_synthesis_node(fake)
    result = await synthesis_node(
        {
            "route_outcome": "TOOL_CALL",
            "subsystem": "RAG",
            "tool_result": {"answer": "Geofencing explanation.", "citations": [{"title": "Geofencing Feature Guide"}], "llm_invoked": True},
        }
    )
    assert result["response_text"] == "Geofencing explanation."
    assert result["citations"] == [{"title": "Geofencing Feature Guide"}]
    assert fake.received_calls == [], "RAG's answer is already final text — synthesis must not call the LLM again"


async def test_synthesis_node_phrases_raw_mongo_data_via_llm():
    fake = FakeLLMProvider(canned_response="You made 2 trips covering 25 km total.")
    synthesis_node = nodes.make_synthesis_node(fake)
    result = await synthesis_node(
        {
            "route_outcome": "TOOL_CALL",
            "subsystem": "MONGO_REPO",
            "utterance": "How many trips did I make?",
            "tool_result": [{"distance_km": 12.5}, {"distance_km": 12.5}],
        }
    )
    assert result["response_text"] == "You made 2 trips covering 25 km total."
    assert len(fake.received_calls) == 1


async def test_memory_update_node_persists_new_active_vehicle(db):
    session_repo = SessionRepository(db)
    company_id, user_id, vehicle_id = ObjectId(), ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)
    session = await session_repo.create(company_id, user_id, now)

    node = nodes.make_memory_update_node(session_repo)
    await node(
        {
            "company_id": str(company_id),
            "session_id": str(session["_id"]),
            "now": now,
            "entities": {"vehicle_id": str(vehicle_id)},
        }
    )

    active_entities, _ = await session_repo.get_active_entities(company_id, session["_id"])
    assert active_entities["vehicle_id"] == vehicle_id
