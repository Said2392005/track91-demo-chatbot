"""
End-to-end RAG pipeline tests, using FakeLLMProvider (no live API key). The critical assertion
throughout: for the two fallback branches, the LLM is never invoked at all — verified by
checking FakeLLMProvider.received_calls, not just the returned text.
"""

import chromadb
import pytest

from app.kb.chunker import load_and_chunk_source_dir
from app.kb.ingest import ingest_chunks
from app.llm.providers.fake import FakeLLMProvider
from app.rag.fallback import NO_RELEVANT_CONTENT_RESPONSE, PRICING_NO_APPROVED_DOC_RESPONSE
from app.rag.pipeline import answer_kb_query
from tests.test_kb_ingestion import KB_SOURCE_DIR


@pytest.fixture(scope="module")
def ingested_collection():
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection("kb_chunks_rag_pipeline_test")
    chunks = load_and_chunk_source_dir(KB_SOURCE_DIR)
    ingest_chunks(chunks, collection=collection)
    return collection


async def test_feature_guide_query_invokes_llm_with_citations(ingested_collection):
    fake = FakeLLMProvider(canned_response="Geofencing lets you draw a boundary. [Source 1]")
    result = await answer_kb_query(
        "How does geofencing work?", "feature_guide", fake, collection=ingested_collection
    )
    assert result.llm_invoked is True
    assert len(fake.received_calls) == 1
    assert result.answer == "Geofencing lets you draw a boundary. [Source 1]"
    assert result.citations
    assert result.citations[0]["title"] == "Geofencing Feature Guide"


async def test_pricing_approved_case_invokes_llm(ingested_collection):
    fake = FakeLLMProvider(canned_response="The Pro plan is ₹899/vehicle/month. [Source 1]")
    result = await answer_kb_query(
        "How much does the Pro plan cost per month?", "pricing", fake, collection=ingested_collection
    )
    assert result.llm_invoked is True
    assert len(fake.received_calls) == 1
    assert all(c["title"] == "Track91 Pricing Sheet" for c in result.citations)


async def test_pricing_ambiguous_query_only_ever_uses_approved_content(ingested_collection):
    """This query's top embedding hit is the UNAPPROVED draft doc (verified: it ranks #1 by
    raw distance, ahead of the approved sheet) — the KB only has 9 pricing chunks total, so
    top-k retrieval always surfaces at least one approved chunk too (here, the approved sheet's
    own "contact sales for custom volume" guidance), meaning this specific query does not hit
    the full zero-approved-doc fallback. What must still hold, and is asserted here: the
    unapproved chunk's content never reaches generation regardless of its rank — every citation
    traces back to the approved sheet only. The pure zero-approved-chunks fallback is tested
    separately below against an isolated collection, where it's actually reachable."""
    fake = FakeLLMProvider(canned_response="For fleets above 500 vehicles, please contact sales. [Source 1]")
    result = await answer_kb_query(
        "What is your custom pricing rate for 1000 or more vehicles?",
        "pricing",
        fake,
        collection=ingested_collection,
    )
    assert result.llm_invoked is True
    assert result.citations, "expected the approved sheet's contact-sales guidance to be used"
    assert all(c["title"] == "Track91 Pricing Sheet" for c in result.citations)


async def test_pricing_no_approved_doc_at_all_never_calls_llm():
    """Isolated collection containing ONLY the unapproved draft doc's chunks — guarantees the
    approved_pricing filter yields nothing, regardless of retrieval/ranking, so this
    deterministically exercises the pure fallback branch that the mixed-KB test above cannot
    reliably reach (see its docstring)."""
    from app.kb.chunker import chunk_document, parse_source_file

    draft_doc = parse_source_file(KB_SOURCE_DIR / "pricing" / "enterprise-pricing-draft-notes.md")
    draft_chunks = chunk_document(draft_doc)
    assert draft_chunks and all(c.approved_pricing is False for c in draft_chunks)

    client = chromadb.EphemeralClient()
    unapproved_only_collection = client.get_or_create_collection("kb_chunks_unapproved_only_test")
    ingest_chunks(draft_chunks, collection=unapproved_only_collection)

    fake = FakeLLMProvider(canned_response="this must never be returned")
    result = await answer_kb_query(
        "What is your custom pricing rate for 1000 or more vehicles?",
        "pricing",
        fake,
        collection=unapproved_only_collection,
    )

    assert result.llm_invoked is False
    assert result.answer == PRICING_NO_APPROVED_DOC_RESPONSE
    assert result.citations == []
    assert fake.received_calls == [], "LLM must never be invoked when no approved pricing chunk exists"


async def test_no_relevant_content_case_never_calls_llm_on_empty_collection():
    empty_client = chromadb.EphemeralClient()
    empty_collection = empty_client.get_or_create_collection("kb_chunks_empty_test")
    fake = FakeLLMProvider(canned_response="this must never be returned")

    result = await answer_kb_query("anything at all", "feature_guide", fake, collection=empty_collection)

    assert result.llm_invoked is False
    assert result.answer == NO_RELEVANT_CONTENT_RESPONSE
    assert fake.received_calls == []


async def test_app_faq_query_end_to_end(ingested_collection):
    fake = FakeLLMProvider(canned_response="Go to Fleet > Devices > Add Device. [Source 1]")
    result = await answer_kb_query(
        "How do I register a new GPS device?", "app_faq", fake, collection=ingested_collection
    )
    assert result.llm_invoked is True
    assert result.citations[0]["title"] == "Track91 App FAQ"


async def test_reranking_is_off_by_default(monkeypatch, ingested_collection):
    """settings.rag_use_reranker defaults to False (see app/core/config.py — measured worse
    than raw retrieval on this KB, docs/phase-7-rag-pipeline/rag-pipeline.md). Spies on
    app.rag.pipeline.rerank to prove it's genuinely not called by default, not just that the
    answer happens to look right either way."""
    import app.rag.pipeline as pipeline_module

    calls = []
    monkeypatch.setattr(pipeline_module, "rerank", lambda *a, **k: calls.append(1) or [])

    fake = FakeLLMProvider(canned_response="answer")
    await answer_kb_query("How does geofencing work?", "feature_guide", fake, collection=ingested_collection)

    assert calls == []


async def test_reranking_can_be_explicitly_enabled(monkeypatch, ingested_collection):
    import app.rag.pipeline as pipeline_module

    real_rerank = pipeline_module.rerank
    calls = []

    def spy(*args, **kwargs):
        calls.append(1)
        return real_rerank(*args, **kwargs)

    monkeypatch.setattr(pipeline_module, "rerank", spy)

    fake = FakeLLMProvider(canned_response="answer")
    result = await answer_kb_query(
        "How does geofencing work?",
        "feature_guide",
        fake,
        collection=ingested_collection,
        use_reranking=True,
    )

    assert calls == [1]
    assert result.llm_invoked is True
