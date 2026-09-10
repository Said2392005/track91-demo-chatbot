"""
The RAG pipeline: retrieve -> re-rank -> assemble (gated for `pricing`) -> generate | fallback.

For the two fallback branches (PRICING with no approved doc, or no relevant content at all),
`generate_cited_answer` / `llm.generate()` is never called — not skipped by a prompt telling
the LLM to refuse, but literally absent from the code path, per the Phase 2 sequence diagram's
"[PRICING gate] ... LLMProvider is never called with unapproved context for a PRICING-shaped
query" and the Phase 5 hard requirement in docs/phase-4-knowledge-base/source-inventory.md.
"""

from dataclasses import dataclass

from chromadb.api.models.Collection import Collection

from app.core.config import settings
from app.kb.retrieve import retrieve
from app.llm.base import LLMProvider
from app.rag.context_assembler import assemble_context, assemble_pricing_context
from app.rag.fallback import NO_RELEVANT_CONTENT_RESPONSE, PRICING_NO_APPROVED_DOC_RESPONSE
from app.rag.generation import generate_cited_answer
from app.rag.reranker import rerank


@dataclass
class RAGResult:
    answer: str
    citations: list[dict]
    llm_invoked: bool


async def answer_kb_query(
    query: str,
    category: str,
    llm: LLMProvider,
    collection: Collection | None = None,
    top_k: int = 6,
    # Was 4; reduced for token cost (a token-usage investigation, not a prior bug) after
    # measuring real Groq prompt_tokens on representative queries: 4->3 saved ~90 tokens/call
    # (~17%), with golden-set citation groundedness *improving* (81.8% -> 100%) rather than
    # dropping — the 4th, least-relevant chunk was apparently what the two previously-failing
    # cases (app_faq_1, troubleshooting_2) were citing. 2 was also measured (saves ~173
    # tokens/call total, also 100% on the golden set) but not shipped: the 45-case golden set
    # doesn't cover every real phrasing, and 2 chunks is a much thinner real-world margin than
    # 3 for a token savings only marginally larger than 4->3 already captured. Note: top_k
    # (the retrieval POOL size, currently 6) has zero effect on prompt token cost by itself —
    # confirmed empirically — since assemble_context()/assemble_pricing_context() always
    # truncate to context_top_n regardless of pool size; top_k only matters for having enough
    # candidates for the PRICING gate to filter through (see context_assembler.py).
    context_top_n: int = 3,
    use_reranking: bool | None = None,
) -> RAGResult:
    retrieved = retrieve(query, top_k=top_k, collection=collection)

    # Opt-in (settings.rag_use_reranker, default False) — measured worse than raw retrieval at
    # this KB's size; see docs/phase-7-rag-pipeline/rag-pipeline.md. context_assembler.py
    # accepts either chunk type unchanged (see its ScoredChunk protocol), so this branch is the
    # only place re-ranking's presence/absence matters.
    if use_reranking if use_reranking is not None else settings.rag_use_reranker:
        candidates = rerank(query, retrieved)
    else:
        candidates = retrieved

    if category == "pricing":
        context = assemble_pricing_context(candidates, top_n=context_top_n)
        if context is None:
            return RAGResult(answer=PRICING_NO_APPROVED_DOC_RESPONSE, citations=[], llm_invoked=False)
    else:
        context = assemble_context(candidates, top_n=context_top_n)
        if context is None:
            return RAGResult(answer=NO_RELEVANT_CONTENT_RESPONSE, citations=[], llm_invoked=False)

    answer = await generate_cited_answer(query, context, llm)
    return RAGResult(answer=answer, citations=context.citations, llm_invoked=True)
