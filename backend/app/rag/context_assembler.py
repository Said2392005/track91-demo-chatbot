"""
Context assembly — formats re-ranked chunks into a citable context block for generation.

Owns the PRICING gate (hard requirement, carried forward from Phase 5's retrieval smoke test
finding that approved/unapproved pricing chunks can be ~0.005 apart by embedding distance, and
locked into docs/phase-4-knowledge-base/source-inventory.md): for a `pricing`-category
retrieval, this module filters to `approved_pricing: true` chunks BEFORE any rank-based
selection — never picks the answering chunk by similarity/relevance rank alone. If nothing
survives that filter, assemble_pricing_context() returns None, which the caller
(app/rag/pipeline.py) must treat as "no approved doc" and skip calling the LLM entirely — not
just prompt it to refuse.
"""

from dataclasses import dataclass
from typing import Protocol


class ScoredChunk(Protocol):
    """Structural type covering both RetrievedChunk (app/kb/retrieve.py) and RankedChunk
    (app/rag/reranker.py) — this module only ever reads chunk_id/text/metadata, never the
    ranking-specific fields (.distance vs .relevance_score), so it works unchanged whether
    re-ranking (settings.rag_use_reranker) is enabled or not."""

    chunk_id: str
    text: str
    metadata: dict


@dataclass
class AssembledContext:
    context_text: str
    citations: list[dict]
    chunks_used: list[ScoredChunk]


def _format(chunks: list[ScoredChunk]) -> AssembledContext:
    blocks = []
    citations = []
    for i, chunk in enumerate(chunks, start=1):
        title = chunk.metadata.get("title", "Unknown source")
        section = chunk.metadata.get("section_title", "")
        blocks.append(f"[Source {i}: {title} — {section}]\n{chunk.text}")
        citations.append({"chunk_id": chunk.chunk_id, "title": title, "section_title": section})
    return AssembledContext(context_text="\n\n".join(blocks), citations=citations, chunks_used=chunks)


def assemble_context(chunks: list[ScoredChunk], top_n: int = 4) -> AssembledContext | None:
    """General-purpose (non-gated) assembly for every KB category except `pricing`."""
    if not chunks:
        return None
    return _format(chunks[:top_n])


def assemble_pricing_context(chunks: list[ScoredChunk], top_n: int = 4) -> AssembledContext | None:
    """PRICING-specific: filter to approved_pricing=True first, THEN select/rank-limit. An
    unapproved chunk ranking highest must never end up in the assembled context — filtering
    after truncation would let exactly that happen."""
    approved = [c for c in chunks if c.metadata.get("approved_pricing") is True]
    if not approved:
        return None
    return _format(approved[:top_n])
