"""
Full multi-turn integration tests — Phase 10 testing requirement. Run through the actual
compiled graph (app.agent.graph.build_graph), each turn a separate `ainvoke()` call sharing
only a thread_id (session_id) — the way two separate HTTP requests actually would — using a
REAL Mongo-backed checkpointer (langgraph-checkpoint-mongodb), not compile() without one. This
specifically exercises the ObjectId-serialization constraint discovered while designing
app/agent/serialization.py: a checkpointer-less graph would never catch a state field that
fails to checkpoint-serialize.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import chromadb
import pytest
from bson import ObjectId
from langgraph.checkpoint.mongodb.saver import MongoDBSaver
from pymongo import MongoClient

from app.agent.graph import build_graph
from app.core.config import settings
from app.db.repositories.session_repository import SessionRepository
from app.kb.chunker import load_and_chunk_source_dir
from app.kb.ingest import ingest_chunks
from app.llm.providers.fake import FakeLLMProvider
from app.nlu.intent_classifier import RuleBasedIntentClassifier
from app.tools.fleet_gps_client import MockFleetGPSClient
from tests.test_kb_ingestion import KB_SOURCE_DIR

TEST_MONGO_URI = os.environ.get("TEST_MONGO_URI", "mongodb://127.0.0.1:27017")


@pytest.fixture
def real_checkpointer():
    """A genuine MongoDBSaver against the test Mongo instance — not compile() with no
    checkpointer, which would silently hide any state-serialization problem."""
    sync_client = MongoClient(TEST_MONGO_URI)
    db_name = f"test_graph_checkpoints_{uuid.uuid4().hex[:8]}"
    saver = MongoDBSaver(sync_client, db_name=db_name, ttl=settings.session_ttl_seconds)
    yield saver
    sync_client.drop_database(db_name)


@pytest.fixture
async def kb_collection():
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection("kb_chunks_agent_graph_test")
    ingest_chunks(load_and_chunk_source_dir(KB_SOURCE_DIR), collection=collection)
    return collection


def _graph(db, kb_collection, checkpointer, llm=None):
    return build_graph(
        classifier=RuleBasedIntentClassifier(),
        db=db,
        llm=llm or FakeLLMProvider(canned_response="generated answer"),
        gps_client=MockFleetGPSClient(),
        kb_collection=kb_collection,
        session_repo=SessionRepository(db),
        checkpointer=checkpointer,
    )


async def test_its_speed_coreference_resolves_across_turns(db, kb_collection, real_checkpointer):
    """The scripted scenario requested for this phase, now proven through the actual graph
    (not the manual glue used for the equivalent Phase 8 test)."""
    company_id, vehicle_id = ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)
    await db.vehicles.insert_one(
        {"_id": vehicle_id, "company_id": company_id, "plate_number": "MH12AB1234", "status": "active", "created_at": now}
    )
    session = await SessionRepository(db).create(company_id, ObjectId(), now)
    session_id = session["_id"]

    graph = _graph(db, kb_collection, real_checkpointer)
    config = {"configurable": {"thread_id": str(session_id)}}

    turn1 = await graph.ainvoke(
        {"utterance": "Where is MH12AB1234?", "company_id": str(company_id), "session_id": str(session_id), "now": now},
        config=config,
    )
    assert turn1["final_intent"] == "GET_VEHICLE_LOCATION"
    assert turn1["route_outcome"] == "TOOL_CALL"
    assert "response_text" in turn1

    turn2 = await graph.ainvoke(
        {
            "utterance": "What's its speed?",
            "company_id": str(company_id),
            "session_id": str(session_id),
            "now": now + timedelta(minutes=2),
        },
        config=config,
    )

    assert turn2["raw_intent"] == "GET_VEHICLE_SPEED"
    assert turn2["final_intent"] == "GET_VEHICLE_SPEED", "must resolve 'its' via memory, not fall to clarification"
    assert turn2["entities"]["vehicle_id"] == str(vehicle_id)
    assert turn2["route_outcome"] == "TOOL_CALL"
    assert turn2["subsystem"] == "LIVE_API"


async def test_its_speed_does_not_resolve_after_active_entity_expiry(db, kb_collection, real_checkpointer):
    company_id, vehicle_id = ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)
    await db.vehicles.insert_one(
        {"_id": vehicle_id, "company_id": company_id, "plate_number": "MH12AB1234", "status": "active", "created_at": now}
    )
    session = await SessionRepository(db).create(company_id, ObjectId(), now)
    session_id = session["_id"]

    graph = _graph(db, kb_collection, real_checkpointer)
    config = {"configurable": {"thread_id": str(session_id)}}

    await graph.ainvoke(
        {"utterance": "Where is MH12AB1234?", "company_id": str(company_id), "session_id": str(session_id), "now": now},
        config=config,
    )

    much_later = now + timedelta(seconds=settings.active_entity_ttl_seconds + 60)
    turn2 = await graph.ainvoke(
        {"utterance": "What's its speed?", "company_id": str(company_id), "session_id": str(session_id), "now": much_later},
        config=config,
    )

    assert turn2["route_outcome"] == "CLARIFICATION_NEEDED"
    assert "vehicle" in turn2["response_text"].lower()
    assert "tool_result" not in turn2 or turn2.get("tool_result") is None


async def test_greeting_then_pricing_question_across_turns(db, kb_collection, real_checkpointer):
    """Multi-turn continuity for a non-coreference case, and the PRICING gate reachable
    through the full graph end to end."""
    company_id = ObjectId()
    now = datetime.now(timezone.utc)
    session = await SessionRepository(db).create(company_id, ObjectId(), now)
    session_id = session["_id"]

    fake = FakeLLMProvider(canned_response="The Pro plan is ₹899/vehicle/month. [Source 1]")
    graph = _graph(db, kb_collection, real_checkpointer, llm=fake)
    config = {"configurable": {"thread_id": str(session_id)}}

    turn1 = await graph.ainvoke(
        {"utterance": "Hi there", "company_id": str(company_id), "session_id": str(session_id), "now": now}, config=config
    )
    assert turn1["route_outcome"] == "NO_TOOL"
    assert "help" in turn1["response_text"].lower()

    turn2 = await graph.ainvoke(
        {
            "utterance": "How much does the Pro plan cost per month?",
            "company_id": str(company_id),
            "session_id": str(session_id),
            "now": now + timedelta(seconds=30),
        },
        config=config,
    )

    assert turn2["final_intent"] == "PRICING"
    assert turn2["subsystem"] == "RAG"
    assert turn2["response_text"] == "The Pro plan is ₹899/vehicle/month. [Source 1]"
    assert turn2["citations"]
    assert all(c["title"] == "Track91 Pricing Sheet" for c in turn2["citations"])


async def test_memory_persists_even_when_synthesis_llm_is_unavailable(db, kb_collection, real_checkpointer):
    """Regression test for a bug found by actually running the server end-to-end with no LLM
    API key configured (the real deployment condition in this environment): turn 1 correctly
    resolves an explicit vehicle_ref, but generation fails (UnavailableLLMProvider). Before the
    fix, LLMUnavailableError propagated out of synthesis_node and aborted the graph before
    memory_update_node ran, silently losing the resolved vehicle. Proven here by switching to a
    WORKING LLM for turn 2 and confirming "its speed" still resolves via memory — if turn 1's
    entity resolution hadn't persisted, turn 2 would need clarification instead."""
    from app.llm.providers.unavailable import UnavailableLLMProvider

    company_id, vehicle_id = ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)
    await db.vehicles.insert_one(
        {"_id": vehicle_id, "company_id": company_id, "plate_number": "MH12AB1234", "status": "active", "created_at": now}
    )
    session = await SessionRepository(db).create(company_id, ObjectId(), now)
    session_id = session["_id"]
    config = {"configurable": {"thread_id": str(session_id)}}

    unavailable_graph = _graph(db, kb_collection, real_checkpointer, llm=UnavailableLLMProvider())
    turn1 = await unavailable_graph.ainvoke(
        {"utterance": "Where is MH12AB1234?", "company_id": str(company_id), "session_id": str(session_id), "now": now},
        config=config,
    )
    assert turn1["route_outcome"] == "TOOL_CALL"
    assert "unable to generate" in turn1["response_text"].lower()

    active_entities, _ = await SessionRepository(db).get_active_entities(company_id, session_id)
    assert active_entities.get("vehicle_id") == vehicle_id, "memory_update_node must still run when synthesis fails"

    working_graph = _graph(
        db, kb_collection, real_checkpointer, llm=FakeLLMProvider(canned_response="It's going 42 km/h.")
    )
    turn2 = await working_graph.ainvoke(
        {
            "utterance": "What's its speed?",
            "company_id": str(company_id),
            "session_id": str(session_id),
            "now": now + timedelta(minutes=1),
        },
        config=config,
    )
    assert turn2["final_intent"] == "GET_VEHICLE_SPEED"
    assert turn2["route_outcome"] == "TOOL_CALL", "must resolve via memory, not need clarification"
