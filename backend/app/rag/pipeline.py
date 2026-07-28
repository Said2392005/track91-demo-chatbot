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
    rerank_top_n: int = 4,
) -> RAGResult:
    retrieved = retrieve(query, top_k=top_k, collection=collection)
    ranked = rerank(query, retrieved)

    if category == "pricing":
        context = assemble_pricing_context(ranked, top_n=rerank_top_n)
        if context is None:
            return RAGResult(answer=PRICING_NO_APPROVED_DOC_RESPONSE, citations=[], llm_invoked=False)
    else:
        context = assemble_context(ranked, top_n=rerank_top_n)
        if context is None:
            return RAGResult(answer=NO_RELEVANT_CONTENT_RESPONSE, citations=[], llm_invoked=False)

    answer = await generate_cited_answer(query, context, llm)
    return RAGResult(answer=answer, citations=context.citations, llm_invoked=True)
