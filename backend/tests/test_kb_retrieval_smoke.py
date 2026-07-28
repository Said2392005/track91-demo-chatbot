"""
Retrieval smoke test — Phase 5 testing requirement (roadmap.md: "retrieval smoke test against
a small golden set"). Checks that ingestion + retrieval round-trips correctly for a handful of
known queries, one per KB category, plus both PRICING gate test cases from
docs/phase-4-knowledge-base/source-inventory.md.

This is NOT precision@k or re-ranking evaluation (that's Phase 7, against a larger golden set).
Assertions use top-3/top-4 membership rather than exact top-1 rank — calibrated against actual
model output (see conversation/commit history), since MiniLM's embedding-only ranking is close
between semantically adjacent chunks (verified empirically before writing these assertions).
"""

from pathlib import Path

import chromadb
import pytest

from app.kb.chunker import load_and_chunk_source_dir
from app.kb.ingest import ingest_chunks
from app.kb.retrieve import retrieve

KB_SOURCE_DIR = Path(__file__).resolve().parent.parent / "kb_sources"


@pytest.fixture(scope="module")
def ingested_collection():
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection("kb_chunks_retrieval_smoke_test")
    chunks = load_and_chunk_source_dir(KB_SOURCE_DIR)
    ingest_chunks(chunks, collection=collection)
    return collection


def test_app_faq_query_retrieves_matching_faq_chunk(ingested_collection):
    hits = retrieve("How do I register a new GPS device?", top_k=3, collection=ingested_collection)
    chunk_ids = [h.chunk_id for h in hits]
    assert "track91-app-faq::q-how-do-i-register-a-new-gps-device" in chunk_ids
    assert all(h.metadata["category"] == "app_faq" for h in hits)


def test_troubleshooting_query_retrieves_troubleshooting_doc(ingested_collection):
    hits = retrieve("My GPS device shows offline, what should I do?", top_k=3, collection=ingested_collection)
    assert hits[0].metadata["doc_id"] == "gps-device-offline-troubleshooting"
    assert all(h.metadata["doc_id"] == "gps-device-offline-troubleshooting" for h in hits)


def test_feature_guide_query_retrieves_geofencing_doc(ingested_collection):
    hits = retrieve("How does geofencing work?", top_k=3, collection=ingested_collection)
    assert hits[0].metadata["doc_id"] == "geofencing-feature-guide"


def test_policy_query_retrieves_retention_policy_doc(ingested_collection):
    hits = retrieve("How long is trip and location history retained?", top_k=3, collection=ingested_collection)
    assert hits[0].metadata["doc_id"] == "data-retention-policy"
    assert hits[0].metadata["section_title"] == "Trip & Location History Retention"


def test_pricing_gate_case_approved_doc_exists(ingested_collection):
    """PRICING gate case 1 (source-inventory.md): a Pro-plan pricing question should retrieve
    the approved pricing sheet as the clear top hit — the Phase 7 gate should pass here."""
    hits = retrieve("How much does the Pro plan cost per month?", top_k=3, collection=ingested_collection)
    assert hits[0].metadata["doc_id"] == "track91-pricing-sheet"
    assert hits[0].metadata["approved_pricing"] is True


def test_pricing_gate_case_no_approved_doc(ingested_collection):
    """PRICING gate case 2 (source-inventory.md): a >1000-vehicle custom pricing question is
    only really answerable from the unapproved draft doc. Retrieval surfaces it (proving the
    scenario is real and retrievable) — Phase 7's gate is what must then reject it and fall
    back to a contact-support response, since not everything retrieved here is approved."""
    hits = retrieve(
        "What is your custom pricing rate for 1000 or more vehicles?", top_k=4, collection=ingested_collection
    )
    draft_hits = [h for h in hits if h.metadata["doc_id"] == "enterprise-pricing-draft-notes"]
    assert draft_hits, "expected the unapproved draft pricing doc to be retrieved for this query"
    assert all(h.metadata["approved_pricing"] is False for h in draft_hits)
    # The scenario only matters if retrieval doesn't return ONLY approved chunks — otherwise
    # there'd be nothing for Phase 7's gate to actually filter out.
    assert any(h.metadata["approved_pricing"] is False for h in hits)
