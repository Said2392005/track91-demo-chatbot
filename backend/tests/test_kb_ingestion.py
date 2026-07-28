"""
Idempotency test — Phase 5 testing requirement (roadmap.md).

Runs ingestion twice against the real 28-chunk KB in backend/kb_sources/ and asserts the
second run does not duplicate anything: same chunk count, and every chunk is skipped as
unchanged (content_hash match) rather than re-embedded. Also verifies that editing a chunk's
content and re-ingesting upserts in place (still no duplicates) rather than appending a second
copy under a new ID.

Uses a real in-memory ChromaDB collection (chromadb.EphemeralClient), not a mock — the
behavior under test (upsert-by-ID semantics) is genuine Chroma server behavior.
"""

from pathlib import Path

import chromadb
import pytest

from app.kb.chunker import load_and_chunk_source_dir
from app.kb.ingest import ingest_chunks

KB_SOURCE_DIR = Path(__file__).resolve().parent.parent / "kb_sources"
EXPECTED_CHUNK_COUNT = 28


@pytest.fixture
def fresh_collection():
    client = chromadb.EphemeralClient()
    return client.get_or_create_collection("kb_chunks_idempotency_test")


def test_source_dir_produces_expected_chunk_count():
    chunks = load_and_chunk_source_dir(KB_SOURCE_DIR)
    assert len(chunks) == EXPECTED_CHUNK_COUNT

    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids)), "chunk IDs must be unique"


def test_ingestion_is_idempotent(fresh_collection):
    chunks = load_and_chunk_source_dir(KB_SOURCE_DIR)

    first_run = ingest_chunks(chunks, collection=fresh_collection)
    assert first_run["total_chunks"] == EXPECTED_CHUNK_COUNT
    assert first_run["embedded"] == EXPECTED_CHUNK_COUNT
    assert first_run["skipped_unchanged"] == 0
    assert fresh_collection.count() == EXPECTED_CHUNK_COUNT

    second_run = ingest_chunks(chunks, collection=fresh_collection)
    assert second_run["total_chunks"] == EXPECTED_CHUNK_COUNT
    assert second_run["embedded"] == 0, "unchanged chunks must not be re-embedded"
    assert second_run["skipped_unchanged"] == EXPECTED_CHUNK_COUNT
    assert fresh_collection.count() == EXPECTED_CHUNK_COUNT, "re-running must not duplicate chunks"


def test_editing_a_chunk_upserts_in_place_not_duplicates(fresh_collection):
    chunks = load_and_chunk_source_dir(KB_SOURCE_DIR)
    ingest_chunks(chunks, collection=fresh_collection)
    assert fresh_collection.count() == EXPECTED_CHUNK_COUNT

    edited = chunks[0]
    original_hash = edited.content_hash
    edited.text = edited.text + " (edited for idempotency test)"
    import hashlib

    edited.content_hash = hashlib.sha256(edited.text.encode("utf-8")).hexdigest()
    assert edited.content_hash != original_hash

    result = ingest_chunks(chunks, collection=fresh_collection)
    assert result["embedded"] == 1, "only the edited chunk should be re-embedded"
    assert result["skipped_unchanged"] == EXPECTED_CHUNK_COUNT - 1
    assert fresh_collection.count() == EXPECTED_CHUNK_COUNT, "editing must upsert, not append"

    stored = fresh_collection.get(ids=[edited.chunk_id])
    assert stored["documents"][0] == edited.text
