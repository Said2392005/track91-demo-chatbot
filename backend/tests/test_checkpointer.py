"""
LangGraph checkpointer tests — Phase 8 requirement: working, expiring checkpointer wiring.
Points get_checkpointer() at the real test MongoDB (not the default settings.mongo_uri, which
would otherwise try to hit localhost:27017) via monkeypatched settings + cache_clear().
"""

import os
import uuid

import pytest

from app.core.config import settings
from app.memory.checkpointer import get_checkpointer

TEST_MONGO_URI = os.environ.get("TEST_MONGO_URI", "mongodb://127.0.0.1:27017")


@pytest.fixture
def checkpointer(monkeypatch):
    test_db_name = f"test_checkpointer_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(settings, "mongo_uri", TEST_MONGO_URI)
    monkeypatch.setattr(settings, "mongo_db_name", test_db_name)
    get_checkpointer.cache_clear()

    saver = get_checkpointer()
    yield saver

    saver.client.drop_database(test_db_name)
    get_checkpointer.cache_clear()


async def test_checkpoint_round_trip(checkpointer):
    config = {"configurable": {"thread_id": "session-1", "checkpoint_ns": ""}}
    checkpoint = {
        "v": 1,
        "id": "chk-1",
        "ts": "2026-07-28T00:00:00+00:00",
        "channel_values": {"messages": ["hello"]},
        "channel_versions": {},
        "versions_seen": {},
        "pending_sends": [],
    }
    metadata = {"source": "input", "step": 1, "writes": {}, "parents": {}}

    await checkpointer.aput(config, checkpoint, metadata, {})
    tup = await checkpointer.aget_tuple(config)

    assert tup is not None
    assert tup.checkpoint["id"] == "chk-1"
    assert tup.checkpoint["channel_values"] == {"messages": ["hello"]}


async def test_different_threads_do_not_share_checkpoints(checkpointer):
    checkpoint_a = {
        "v": 1,
        "id": "chk-a",
        "ts": "2026-07-28T00:00:00+00:00",
        "channel_values": {"messages": ["from thread a"]},
        "channel_versions": {},
        "versions_seen": {},
        "pending_sends": [],
    }
    metadata = {"source": "input", "step": 1, "writes": {}, "parents": {}}

    config_a = {"configurable": {"thread_id": "thread-a", "checkpoint_ns": ""}}
    config_b = {"configurable": {"thread_id": "thread-b", "checkpoint_ns": ""}}

    await checkpointer.aput(config_a, checkpoint_a, metadata, {})
    tup_b = await checkpointer.aget_tuple(config_b)

    assert tup_b is None


def test_checkpoint_collection_has_ttl_index_matching_session_ttl(checkpointer):
    indexes = list(checkpointer.checkpoint_collection.list_indexes())
    ttl_indexes = [idx for idx in indexes if "expireAfterSeconds" in idx]
    assert len(ttl_indexes) == 1, "expected exactly one TTL index on the checkpoint collection"
    assert ttl_indexes[0]["expireAfterSeconds"] == settings.session_ttl_seconds
