"""
PRICING gate tests — the hard requirement carried forward from Phase 5/2: for pricing
retrieval, filter to approved_pricing=True BEFORE any rank-based selection, never select the
answering chunk by similarity/relevance rank alone.
"""

from app.rag.context_assembler import assemble_context, assemble_pricing_context
from app.rag.reranker import RankedChunk


def _ranked(chunk_id, text, score, **meta):
    return RankedChunk(chunk_id=chunk_id, text=text, metadata=meta, relevance_score=score)


def test_assemble_context_empty_input_returns_none():
    assert assemble_context([]) is None


def test_assemble_context_includes_citations():
    chunks = [_ranked("c1", "Some KB text", 9.0, title="Doc Title", section_title="Section A")]
    context = assemble_context(chunks)
    assert "Doc Title" in context.context_text
    assert context.citations == [{"chunk_id": "c1", "title": "Doc Title", "section_title": "Section A"}]


def test_pricing_gate_passes_when_approved_chunk_present():
    chunks = [_ranked("approved-1", "Pro plan costs X", 9.0, approved_pricing=True, title="Pricing Sheet")]
    context = assemble_pricing_context(chunks)
    assert context is not None
    assert context.chunks_used[0].chunk_id == "approved-1"


def test_pricing_gate_rejects_when_only_unapproved_chunks_present():
    chunks = [_ranked("draft-1", "Draft custom rate", 9.0, approved_pricing=False, title="Draft Notes")]
    assert assemble_pricing_context(chunks) is None


def test_pricing_gate_filters_out_unapproved_even_when_it_ranks_highest():
    """The scenario that motivates the whole gate: an unapproved chunk can rank ABOVE an
    approved one (Phase 5 measured a 0.005 margin between them). Filtering must happen before
    truncation, not after — otherwise a top_n cutoff could silently drop the approved chunk and
    keep the higher-ranked unapproved one."""
    chunks = [
        _ranked("draft-1", "Draft custom rate, ranks highest", 9.5, approved_pricing=False, title="Draft"),
        _ranked("approved-1", "Approved Enterprise plan info, ranks lower", 9.4, approved_pricing=True, title="Sheet"),
    ]
    context = assemble_pricing_context(chunks, top_n=1)
    assert context is not None
    assert context.chunks_used[0].chunk_id == "approved-1"
    assert all(c.metadata.get("approved_pricing") is True for c in context.chunks_used)


def test_pricing_gate_never_includes_unapproved_chunks_in_mixed_results():
    chunks = [
        _ranked("approved-1", "Approved chunk", 9.0, approved_pricing=True, title="Sheet"),
        _ranked("draft-1", "Unapproved chunk", 8.0, approved_pricing=False, title="Draft"),
    ]
    context = assemble_pricing_context(chunks, top_n=4)
    assert len(context.chunks_used) == 1
    assert context.chunks_used[0].chunk_id == "approved-1"


def test_non_pricing_assembly_does_not_filter_non_pricing_chunks_by_approval():
    """`approved_pricing` defaults to False for every non-pricing chunk by convention
    (metadata-schema.md) — assemble_context() must not treat that as "unapproved, exclude it"
    the way assemble_pricing_context() does, or it would wrongly drop nearly every
    feature_guide/app_faq/troubleshooting/policy chunk that exists."""
    chunks = [_ranked("c1", "Feature guide text", 9.0, approved_pricing=False, category="feature_guide", title="Feature Guide")]
    context = assemble_context(chunks)
    assert context is not None
    assert context.chunks_used[0].chunk_id == "c1"


def test_non_pricing_assembly_excludes_unapproved_pricing_content_specifically():
    """Regression test for a real finding from the Phase 12 eval golden set: a POLICY_QUESTION
    query pulled in a citation from the internal "Draft Enterprise Pricing Notes" doc (category
    "pricing", unapproved) — content explicitly marked as never to be shown to a customer,
    leaking in via an unrelated question because only PRICING-routed queries were gated.
    assemble_context() must exclude category=="pricing" chunks that aren't approved, while still
    including every other category's chunks regardless of their (irrelevant) approved_pricing
    value."""
    chunks = [
        _ranked("policy-1", "Data retention policy text", 9.0, approved_pricing=False, category="policy", title="Data Retention Policy"),
        _ranked("draft-1", "Unapproved draft pricing notes", 8.5, approved_pricing=False, category="pricing", title="Draft Notes"),
    ]
    context = assemble_context(chunks)
    assert context is not None
    assert [c.chunk_id for c in context.chunks_used] == ["policy-1"]


def test_non_pricing_assembly_returns_none_if_only_unapproved_pricing_chunks_survive():
    chunks = [_ranked("draft-1", "Unapproved draft pricing notes", 9.0, approved_pricing=False, category="pricing", title="Draft Notes")]
    assert assemble_context(chunks) is None
