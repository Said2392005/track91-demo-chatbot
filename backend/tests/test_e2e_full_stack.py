"""
Full-stack end-to-end tests — the top of the Phase 12 pyramid. Unlike Phase 11's router-
contract tests (real DB, DI-overridden fake graph) or Phase 10's graph integration tests (real
graph, no HTTP layer), this drives the *actual* FastAPI app object through its *actual*
`lifespan` (via `TestClient` used as a context manager — verified in Phase 12's own development
that this, unlike raw `httpx.ASGITransport`, genuinely triggers startup/shutdown) with a real
Mongo-backed checkpointer and a real ChromaDB collection. The only thing swapped is the LLM
(FakeLLMProvider, monkeypatched into `app.main` before lifespan constructs the graph) — per
the project decision to build Phase 12 against a fake for now (docs/phase-12-testing/testing.md
has the walkthrough for pointing this at a real provider once a key is configured).
"""

import os
import uuid

import chromadb
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

import app.main as main_module
from app.core.config import settings
from app.core.security import hash_password
from app.db.client import get_client
from app.kb.chunker import load_and_chunk_source_dir
from app.kb.ingest import ingest_chunks
from app.llm.providers.fake import FakeLLMProvider
from app.memory.checkpointer import get_checkpointer
from tests.test_kb_ingestion import KB_SOURCE_DIR

TEST_MONGO_URI = os.environ.get("TEST_MONGO_URI", "mongodb://127.0.0.1:27017")


@pytest.fixture
def e2e_client(monkeypatch):
    test_db_name = f"test_e2e_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(settings, "mongo_uri", TEST_MONGO_URI)
    monkeypatch.setattr(settings, "mongo_db_name", test_db_name)
    monkeypatch.setattr(settings, "jwt_secret_key", "e2e-test-secret-at-least-32-bytes-long-not-for-production")
    get_client.cache_clear()
    get_checkpointer.cache_clear()

    chroma_client = chromadb.EphemeralClient()
    kb_collection = chroma_client.get_or_create_collection("kb_chunks_e2e_test")
    ingest_chunks(load_and_chunk_source_dir(KB_SOURCE_DIR), collection=kb_collection)

    fake_llm = FakeLLMProvider(canned_response="E2E canned answer. [Source 1]")
    monkeypatch.setattr(main_module, "get_llm_provider", lambda: fake_llm)
    monkeypatch.setattr(main_module, "get_kb_collection", lambda: kb_collection)

    with TestClient(main_module.app) as client:
        yield client, test_db_name

    get_client.cache_clear()
    get_checkpointer.cache_clear()
    MongoClient(TEST_MONGO_URI).drop_database(test_db_name)


def _seed_demo_user(test_db_name: str, email: str, password: str) -> None:
    from datetime import datetime, timezone

    sync_client = MongoClient(TEST_MONGO_URI)
    sync_client[test_db_name].users.insert_one(
        {
            "company_id": None,  # filled below
            "name": "E2E Test User",
            "email": email,
            "role": "fleet_manager",
            "status": "active",
            "password_hash": hash_password(password),
            "created_at": datetime.now(timezone.utc),
        }
    )
    company_id = sync_client[test_db_name].companies.insert_one(
        {"name": "E2E Test Co", "status": "active", "timezone": "Asia/Kolkata", "created_at": datetime.now(timezone.utc)}
    ).inserted_id
    sync_client[test_db_name].users.update_one({"email": email}, {"$set": {"company_id": company_id}})
    sync_client[test_db_name].vehicles.insert_one(
        {
            "company_id": company_id,
            "plate_number": "MH12AB1234",
            "status": "active",
            "created_at": datetime.now(timezone.utc),
        }
    )
    sync_client.close()


def test_health_and_ready_through_real_lifespan(e2e_client):
    client, _ = e2e_client
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200


def test_full_login_and_chat_round_trip(e2e_client):
    client, db_name = e2e_client
    _seed_demo_user(db_name, "e2e@example.com", "e2e-password")

    login = client.post("/auth/login", json={"email": "e2e@example.com", "password": "e2e-password"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    chat = client.post("/chat", json={"message": "Hi there"}, headers=headers)
    assert chat.status_code == 200
    body = chat.json()
    assert body["intent"] == "GREETING"
    assert "help" in body["response"].lower()

    history = client.get(f"/chat/{body['session_id']}/history", headers=headers)
    assert history.status_code == 200
    assert len(history.json()["messages"]) == 2


def test_its_speed_coreference_through_real_http_and_real_graph(e2e_client):
    """The requested "its speed" scenario, now verified through the actual HTTP API — not the
    graph directly (Phase 10) and not with a DI-overridden fake graph (Phase 11), but the real
    compiled graph behind the real endpoints, with a real Mongo checkpointer persisting state
    between the two HTTP requests."""
    client, db_name = e2e_client
    _seed_demo_user(db_name, "coref@example.com", "e2e-password")
    token = client.post("/auth/login", json={"email": "coref@example.com", "password": "e2e-password"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    turn1 = client.post("/chat", json={"message": "Where is MH12AB1234?"}, headers=headers)
    session_id = turn1.json()["session_id"]
    assert turn1.json()["intent"] == "GET_VEHICLE_LOCATION"

    turn2 = client.post("/chat", json={"message": "What's its speed?", "session_id": session_id}, headers=headers)
    assert turn2.json()["intent"] == "GET_VEHICLE_SPEED", "must resolve via memory, not need clarification"


def test_pricing_gate_through_real_http_stack(e2e_client):
    client, db_name = e2e_client
    _seed_demo_user(db_name, "pricing@example.com", "e2e-password")
    token = client.post("/auth/login", json={"email": "pricing@example.com", "password": "e2e-password"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/chat", json={"message": "How much does the Pro plan cost per month?"}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "PRICING"
    assert body["citations"]
    assert all(c["title"] == "Track91 Pricing Sheet" for c in body["citations"])
