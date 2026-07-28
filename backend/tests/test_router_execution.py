"""
Execution-level router tests: route() decides, execute_tool() actually calls the handler
against real dependencies (mock GPS client, real Mongo, real ChromaDB, FakeLLMProvider — no
mocks for our own code, only for the two things genuinely external to this build: the real
Fleet GPS API and a real LLM API, neither of which exist in this environment).
"""

from datetime import datetime, timezone

import chromadb
import pytest_asyncio
from bson import ObjectId

from app.kb.chunker import chunk_document, load_and_chunk_source_dir, parse_source_file
from app.kb.ingest import ingest_chunks
from app.llm.providers.fake import FakeLLMProvider
from app.rag.fallback import PRICING_NO_APPROVED_DOC_RESPONSE
from app.router.router import execute_tool, route
from app.tools.fleet_gps_client import MockFleetGPSClient
from tests.test_kb_ingestion import KB_SOURCE_DIR


async def test_execute_live_api_tool_returns_mock_gps_data():
    decision = route("GET_VEHICLE_SPEED", {"vehicle_id": ObjectId()})
    assert decision.outcome == "TOOL_CALL"

    result = await execute_tool(decision, gps_client=MockFleetGPSClient(), now=datetime.now(timezone.utc))

    assert "speed_kmph" in result
    assert isinstance(result["speed_kmph"], float)


async def test_execute_mongo_repo_tool_returns_seeded_trips(db):
    company_id, vehicle_id = ObjectId(), ObjectId()
    trip_time = datetime(2026, 7, 15, tzinfo=timezone.utc)
    await db.trips.insert_one(
        {
            "company_id": company_id,
            "vehicle_id": vehicle_id,
            "start_time": trip_time,
            "end_time": trip_time,
            "distance_km": 12.5,
            "created_at": datetime.now(timezone.utc),
        }
    )

    decision = route(
        "GET_TRIP_HISTORY",
        {"vehicle_id": vehicle_id, "date_range": (datetime(2026, 7, 1, tzinfo=timezone.utc), datetime(2026, 8, 1, tzinfo=timezone.utc))},
    )
    assert decision.outcome == "TOOL_CALL"

    result = await execute_tool(decision, company_id=company_id, db=db)

    assert len(result) == 1
    assert result[0]["distance_km"] == 12.5


@pytest_asyncio.fixture(scope="module")
async def ingested_collection():
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection("kb_chunks_router_execution_test")
    chunks = load_and_chunk_source_dir(KB_SOURCE_DIR)
    ingest_chunks(chunks, collection=collection)
    return collection


async def test_execute_rag_kb_tool_generates_cited_answer(ingested_collection):
    decision = route("EXPLAIN_FEATURE", {"kb_topic": "How does geofencing work?"})
    assert decision.outcome == "TOOL_CALL"

    fake = FakeLLMProvider(canned_response="Geofencing draws a boundary. [Source 1]")
    result = await execute_tool(decision, llm=fake, kb_collection=ingested_collection)

    assert result.llm_invoked is True
    assert result.citations[0]["title"] == "Geofencing Feature Guide"


async def test_execute_pricing_tool_approved_case_generates_answer(ingested_collection):
    decision = route("PRICING", {"kb_topic": "How much does the Pro plan cost per month?"})
    fake = FakeLLMProvider(canned_response="₹899/vehicle/month. [Source 1]")

    result = await execute_tool(decision, llm=fake, kb_collection=ingested_collection)

    assert result.llm_invoked is True
    assert all(c["title"] == "Track91 Pricing Sheet" for c in result.citations)


async def test_execute_pricing_tool_no_approved_doc_never_calls_llm():
    """Same gate proven in Phase 7, now proven reachable through the Phase 9 execution path
    specifically — route() -> execute_tool() -> kb_tools.pricing() -> answer_kb_query(...,
    "pricing", ...), not some other path that might bypass the gate."""
    draft_doc = parse_source_file(KB_SOURCE_DIR / "pricing" / "enterprise-pricing-draft-notes.md")
    draft_chunks = chunk_document(draft_doc)

    client = chromadb.EphemeralClient()
    unapproved_only = client.get_or_create_collection("kb_chunks_router_unapproved_only_test")
    ingest_chunks(draft_chunks, collection=unapproved_only)

    decision = route("PRICING", {"kb_topic": "What is your custom pricing rate for 1000 or more vehicles?"})
    fake = FakeLLMProvider(canned_response="this must never be returned")

    result = await execute_tool(decision, llm=fake, kb_collection=unapproved_only)

    assert result.llm_invoked is False
    assert result.answer == PRICING_NO_APPROVED_DOC_RESPONSE
    assert fake.received_calls == []


async def test_execute_general_knowledge_tool_calls_llm_directly():
    decision = route("GENERAL_KNOWLEDGE", {"kb_topic": "What does AIS-140 mean?"})
    assert decision.outcome == "TOOL_CALL"
    assert decision.subsystem == "GENERAL_FALLBACK"

    fake = FakeLLMProvider(canned_response="AIS-140 is an Indian vehicle tracking standard.")
    result = await execute_tool(decision, llm=fake)

    assert result == "AIS-140 is an Indian vehicle tracking standard."
    assert len(fake.received_calls) == 1


async def test_execute_tool_raises_on_non_tool_call_decision():
    decision = route("GREETING", {})
    assert decision.outcome == "NO_TOOL"
    try:
        await execute_tool(decision)
        assert False, "expected ValueError"
    except ValueError:
        pass
