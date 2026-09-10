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


async def test_bare_vehicle_number_completes_pending_clarification(db, kb_collection, real_checkpointer):
    """Real bug, reproduced live: "where is my vehicle?" -> "which vehicle?" -> a bare plate
    number with no verb ("MH12AB1234") must complete the original GET_VEHICLE_LOCATION intent,
    not fall through to OUT_OF_SCOPE/GENERAL_FALLBACK. Proven through the real compiled graph,
    across two separate ainvoke() calls sharing only a thread_id, the way two separate HTTP
    requests actually would."""
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
        {"utterance": "where is my vehicle", "company_id": str(company_id), "session_id": str(session_id), "now": now},
        config=config,
    )
    assert turn1["raw_intent"] == "GET_VEHICLE_LOCATION"
    assert turn1["route_outcome"] == "CLARIFICATION_NEEDED"
    assert "vehicle" in turn1["response_text"].lower()

    turn2 = await graph.ainvoke(
        {
            "utterance": "MH12AB1234",
            "company_id": str(company_id),
            "session_id": str(session_id),
            "now": now + timedelta(seconds=30),
        },
        config=config,
    )
    assert turn2["raw_intent"] == "GET_VEHICLE_LOCATION", "must resume the pending intent, not re-classify to OUT_OF_SCOPE"
    assert turn2["final_intent"] == "GET_VEHICLE_LOCATION"
    assert turn2["entities"]["vehicle_id"] == str(vehicle_id)
    assert turn2["route_outcome"] == "TOOL_CALL"
    assert turn2["subsystem"] == "LIVE_API"

    # Single-turn scoped: a third, unrelated turn must not still be affected by turn1's
    # clarification now that turn2 already consumed (popped) it.
    turn3 = await graph.ainvoke(
        {"utterance": "Hi there", "company_id": str(company_id), "session_id": str(session_id), "now": now + timedelta(minutes=1)},
        config=config,
    )
    assert turn3["raw_intent"] == "GREETING"


async def test_vague_followup_with_no_pronoun_uses_active_entity_not_crash(db, kb_collection, real_checkpointer):
    """Real bug, reproduced live: turn 1 sets an active vehicle explicitly. Turn 2 asks "where
    is my vehicle" — no pronoun ("it"/"its"/"that"/...) for Phase 6's own coreference check to
    catch, and no explicit plate — so Phase 6 leaves final_intent=CLARIFICATION_NEEDED. But
    route() fills the missing vehicle_ref from active_entities unconditionally (its own
    defense-in-depth, not pronoun-gated), so route_outcome=TOOL_CALL. app/agent/nodes.py's
    _decision_from_state previously used final_intent for the executed tool lookup and crashed
    with KeyError('CLARIFICATION_NEEDED') instead of running the GET_VEHICLE_LOCATION tool
    route() had actually decided on. Also covers the follow-up fix: final_intent itself must be
    corrected to GET_VEHICLE_LOCATION (router_node) so what's returned/persisted
    (ChatResponse.intent, chat_messages.intent) matches what actually ran, not Phase 6's
    pre-memory-fill guess — see test_chat_service_persists_corrected_final_intent for the
    persistence-layer version of this same assertion."""
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
    assert turn1["route_outcome"] == "TOOL_CALL"

    turn2 = await graph.ainvoke(
        {
            "utterance": "where is my vehicle",
            "company_id": str(company_id),
            "session_id": str(session_id),
            "now": now + timedelta(seconds=30),
        },
        config=config,
    )
    assert turn2["route_outcome"] == "TOOL_CALL", "route() should fill vehicle_ref from active_entities and actually run the tool"
    assert "tool_result" in turn2 and turn2["tool_result"] is not None
    assert "response_text" in turn2 and turn2["response_text"]
    assert turn2["final_intent"] == "GET_VEHICLE_LOCATION", (
        "the tool that actually ran must be reflected in final_intent, not Phase 6's pre-memory-fill CLARIFICATION_NEEDED guess"
    )


async def test_asking_about_driver_does_not_reuse_active_vehicle_from_memory(db, kb_collection, real_checkpointer):
    """Real bug, reproduced live: turn 1 establishes an active vehicle. Turn 2 asks "where is
    my driver" — classified as GET_VEHICLE_LOCATION via the bare "where is" phrase (a
    pre-existing classifier imprecision, not fixed here), but must NOT silently reuse turn 1's
    vehicle from active_entities to answer it: "driver" names a different entity type than
    what's in memory, so route()'s memory-fill must be suppressed and the turn should ask for
    clarification instead of returning a confident, specific-sounding but wrong-context GPS
    coordinate. This is a worse failure mode than a decline — it looks like a real answer."""
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
    assert turn1["route_outcome"] == "TOOL_CALL"

    turn2 = await graph.ainvoke(
        {
            "utterance": "where is my driver",
            "company_id": str(company_id),
            "session_id": str(session_id),
            "now": now + timedelta(seconds=30),
        },
        config=config,
    )
    assert turn2["route_outcome"] == "CLARIFICATION_NEEDED", "must not answer with turn 1's vehicle — 'driver' is a different entity type"
    assert turn2.get("tool_result") is None


async def test_unrelated_driver_question_after_resolved_vehicle_clarification_is_not_a_stale_resume(
    db, kb_collection, real_checkpointer
):
    """Reported live as a suspected regression from a (never-built) persistence fix: turn 1
    "where is my vehicle and driver" asks to disambiguate the vehicle (two vehicles on the
    company); turn 2 "KA05EF9012" correctly resolves and answers the location; turn 3, a brand
    new and otherwise-unrelated "where is my driver", again returns the vehicle-disambiguation
    prompt — which looked like turn 1's pending_clarification being wrongly resumed against an
    unrelated question.

    Verified live it is NOT that: pop_pending_clarification's atomic $unset clears the field by
    the end of turn 2 (asserted directly against the DB below), so turn 3 starts with no pending
    state at all. It is a fresh, independent misclassification, same root cause and same accepted
    behavior as test_asking_about_driver_does_not_reuse_active_vehicle_from_memory above:
    GET_VEHICLE_LOCATION's bare "where is" TRIGGER_PHRASES entry (trigger_patterns.py) scores
    regardless of subject, so "where is my driver" hits GET_VEHICLE_LOCATION with no vehicle
    resolvable, on its own, with zero connection to turns 1-2. Pinned as its own case because the
    setup (an ambiguous *compound* first turn, resolved over two turns, in the same session) is a
    new combination the existing test doesn't cover, and because the resemblance to a resumed
    clarification is exactly the confusion this test exists to rule out."""
    company_id, v1, v2 = ObjectId(), ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)
    await db.vehicles.insert_many(
        [
            {"_id": v1, "company_id": company_id, "plate_number": "KA05EF9012", "status": "active", "created_at": now},
            {"_id": v2, "company_id": company_id, "plate_number": "MH12AB1234", "status": "active", "created_at": now},
        ]
    )
    session = await SessionRepository(db).create(company_id, ObjectId(), now)
    session_id = session["_id"]

    graph = _graph(db, kb_collection, real_checkpointer)
    config = {"configurable": {"thread_id": str(session_id)}}

    turn1 = await graph.ainvoke(
        {"utterance": "where is my vehicle and driver", "company_id": str(company_id), "session_id": str(session_id), "now": now},
        config=config,
    )
    assert turn1["route_outcome"] == "CLARIFICATION_NEEDED"
    assert turn1["secondary_raw_intent"] is None, "bare singular 'driver' scores 0 — see second_intent_golden_set's KNOWN_MISS case"

    turn2 = await graph.ainvoke(
        {
            "utterance": "KA05EF9012",
            "company_id": str(company_id),
            "session_id": str(session_id),
            "now": now + timedelta(seconds=30),
        },
        config=config,
    )
    assert turn2["route_outcome"] == "TOOL_CALL"
    assert turn2["entities"]["vehicle_id"] == str(v1)

    doc = await db.chat_sessions.find_one({"_id": session_id})
    assert doc.get("pending_clarification") is None, "must be fully cleared before turn 3 — rules out a stale resume as the cause"

    turn3 = await graph.ainvoke(
        {"utterance": "where is my driver", "company_id": str(company_id), "session_id": str(session_id), "now": now + timedelta(minutes=1)},
        config=config,
    )
    assert turn3["raw_intent"] == "GET_VEHICLE_LOCATION", "fresh misclassification via the bare 'where is' phrase, not a resumed intent"
    assert turn3["route_outcome"] == "CLARIFICATION_NEEDED"
    assert turn3.get("tool_result") is None, "must not silently reuse turn 2's vehicle — 'driver' is a different entity type"


async def test_affirm_deny_reply_to_a_real_clarifying_question(db, kb_collection, real_checkpointer):
    """The AFFIRM_DENY gap flagged earlier: awaiting_clarification was only ever set manually
    in tests/the eval golden set, never by a real conversation, so a real "Yes"/"No" reply to a
    real clarifying question always misclassified as OUT_OF_SCOPE instead of AFFIRM_DENY. Now
    driven by the same pending_clarification state as the bare-entity-resume case above."""
    company_id = ObjectId()
    now = datetime.now(timezone.utc)
    session = await SessionRepository(db).create(company_id, ObjectId(), now)
    session_id = session["_id"]

    graph = _graph(db, kb_collection, real_checkpointer)
    config = {"configurable": {"thread_id": str(session_id)}}

    turn1 = await graph.ainvoke(
        {"utterance": "where is my vehicle", "company_id": str(company_id), "session_id": str(session_id), "now": now},
        config=config,
    )
    assert turn1["route_outcome"] == "CLARIFICATION_NEEDED"

    turn2 = await graph.ainvoke(
        {"utterance": "Yes", "company_id": str(company_id), "session_id": str(session_id), "now": now + timedelta(seconds=10)},
        config=config,
    )
    assert turn2["raw_intent"] == "AFFIRM_DENY", "a real 'Yes' reply to a real clarifying question must classify as AFFIRM_DENY"


async def test_dual_intent_both_resolve_cleanly(db, kb_collection, real_checkpointer):
    """Q2's "middle option", wired in: "list drivers and MH12AB1234 location" scores real
    signal for both GET_DRIVER_ROSTER (primary) and GET_VEHICLE_LOCATION (secondary — the plate
    lets vehicle_ref resolve without needing prior session memory). Both tools actually run;
    the merged answer covers both; final_intent reflects both, not just the primary (the same
    "reflect what actually happened" principle the earlier final_intent fix established, now
    applied to the two-intent case)."""
    company_id, vehicle_id = ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)
    await db.vehicles.insert_one(
        {"_id": vehicle_id, "company_id": company_id, "plate_number": "MH12AB1234", "status": "active", "created_at": now}
    )
    await db.drivers.insert_one(
        {"_id": ObjectId(), "company_id": company_id, "name": "Ramesh Kumar", "status": "active", "created_at": now}
    )
    session = await SessionRepository(db).create(company_id, ObjectId(), now)
    session_id = session["_id"]

    fake = FakeLLMProvider(canned_response=["driver roster answer", "vehicle location answer"])
    graph = _graph(db, kb_collection, real_checkpointer, llm=fake)
    config = {"configurable": {"thread_id": str(session_id)}}

    turn = await graph.ainvoke(
        {
            "utterance": "list drivers and MH12AB1234 location",
            "company_id": str(company_id),
            "session_id": str(session_id),
            "now": now,
        },
        config=config,
    )

    assert turn["raw_intent"] == "GET_DRIVER_ROSTER"
    assert turn["secondary_raw_intent"] == "GET_VEHICLE_LOCATION"
    assert turn["route_outcome"] == "TOOL_CALL"
    assert turn["secondary_route_outcome"] == "TOOL_CALL"
    assert turn["final_intent"] == "GET_DRIVER_ROSTER+GET_VEHICLE_LOCATION"
    assert "driver roster answer" in turn["response_text"]
    assert "vehicle location answer" in turn["response_text"]
    assert turn["tool_result"] is not None
    assert turn["secondary_tool_result"] is not None


async def test_dual_intent_primary_resolves_secondary_needs_clarification(db, kb_collection, real_checkpointer):
    """"list drivers and vehicle location" (no plate this time) — GET_DRIVER_ROSTER (primary)
    resolves cleanly, GET_VEHICLE_LOCATION (secondary) has nothing to resolve vehicle_ref
    against. Per the documented design decision: the primary is answered in full, not withheld
    behind a combined question, and the secondary's clarifying question is appended. A bare
    follow-up plate number next turn must then resume GET_VEHICLE_LOCATION via the same
    pending-clarification mechanism a single-intent turn already uses — proving
    memory_update_node's new pending_clarification write for the secondary actually works, not
    just that it was called."""
    company_id, vehicle_id = ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)
    await db.vehicles.insert_one(
        {"_id": vehicle_id, "company_id": company_id, "plate_number": "MH12AB1234", "status": "active", "created_at": now}
    )
    await db.drivers.insert_one(
        {"_id": ObjectId(), "company_id": company_id, "name": "Ramesh Kumar", "status": "active", "created_at": now}
    )
    session = await SessionRepository(db).create(company_id, ObjectId(), now)
    session_id = session["_id"]

    fake = FakeLLMProvider(canned_response="driver roster answer")
    graph = _graph(db, kb_collection, real_checkpointer, llm=fake)
    config = {"configurable": {"thread_id": str(session_id)}}

    turn1 = await graph.ainvoke(
        {"utterance": "list drivers and vehicle location", "company_id": str(company_id), "session_id": str(session_id), "now": now},
        config=config,
    )

    assert turn1["raw_intent"] == "GET_DRIVER_ROSTER"
    assert turn1["route_outcome"] == "TOOL_CALL", "the primary must still execute and answer in full"
    assert turn1["secondary_raw_intent"] == "GET_VEHICLE_LOCATION"
    assert turn1["secondary_route_outcome"] == "CLARIFICATION_NEEDED"
    assert turn1["final_intent"] == "GET_DRIVER_ROSTER+CLARIFICATION_NEEDED"
    assert "driver roster answer" in turn1["response_text"], "primary answer must not be withheld"
    assert "vehicle" in turn1["response_text"].lower(), "secondary's clarifying question must be appended"

    pending = await SessionRepository(db).pop_pending_clarification(company_id, session_id)
    assert pending == {"intent": "GET_VEHICLE_LOCATION", "missing": "vehicle_ref"}
    # Restore it — the real flow reads it via entry_node on the next turn, not via this
    # assertion's own pop.
    await SessionRepository(db).set_pending_clarification(company_id, session_id, "GET_VEHICLE_LOCATION", "vehicle_ref", now)

    turn2 = await graph.ainvoke(
        {
            "utterance": "MH12AB1234",
            "company_id": str(company_id),
            "session_id": str(session_id),
            "now": now + timedelta(seconds=30),
        },
        config=config,
    )
    assert turn2["raw_intent"] == "GET_VEHICLE_LOCATION", "bare plate must resume the secondary's pending intent"
    assert turn2["route_outcome"] == "TOOL_CALL"
    assert turn2["entities"]["vehicle_id"] == str(vehicle_id)


async def test_second_intent_negatives_execute_as_pure_single_intent_through_the_full_graph(db, kb_collection, real_checkpointer):
    """The exact 7 negative cases from app/eval/second_intent_golden_set.py (measured 0%
    false-positive standalone) run through the REAL graph — proving the wiring, not just the
    detector function in isolation, correctly treats them as single-intent turns: no secondary
    fields populated, no appended clarifying question, no "+" in final_intent."""
    from app.eval.second_intent_golden_set import SECOND_INTENT_GOLDEN_SET

    negatives = [c for c in SECOND_INTENT_GOLDEN_SET if not c.expect_second_intent]
    assert len(negatives) >= 7

    company_id, vehicle_id = ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)
    await db.vehicles.insert_one(
        {"_id": vehicle_id, "company_id": company_id, "plate_number": "MH12AB1234", "status": "active", "created_at": now}
    )
    await db.vehicles.insert_one(
        {"_id": ObjectId(), "company_id": company_id, "plate_number": "MH14CD5678", "status": "active", "created_at": now}
    )
    for name in ("Ramesh Kumar", "Suresh Patil"):
        await db.drivers.insert_one({"_id": ObjectId(), "company_id": company_id, "name": name, "status": "active", "created_at": now})

    fake = FakeLLMProvider(canned_response="canned answer. [Source 1]")
    graph = _graph(db, kb_collection, real_checkpointer, llm=fake)

    for case in negatives:
        session = await SessionRepository(db).create(company_id, ObjectId(), now)
        config = {"configurable": {"thread_id": str(session["_id"])}}
        turn = await graph.ainvoke(
            {"utterance": case.utterance, "company_id": str(company_id), "session_id": str(session["_id"]), "now": now},
            config=config,
        )
        assert turn.get("secondary_route_outcome") is None, f"{case.case_id}: {case.utterance!r} wrongly detected a secondary intent"
        assert "+" not in (turn.get("final_intent") or ""), f"{case.case_id}: final_intent should not be compound"
