"""
RAG tool handlers — one per KB intent, each an explicit, individually-named call into
app.rag.pipeline.answer_kb_query() with its category hardcoded. Deliberately not a single
generic dispatcher keyed by a runtime lookup: `pricing()` calling `answer_kb_query(..., "pricing",
...)` in its own function body is what makes it possible to prove, just by reading this file,
that the PRICING intent always goes through the gated RAG pipeline and never a bare LLM call —
the same property tests/test_router_execution.py verifies by spying on this exact call.

EXPLAIN_ALERT_TYPE maps to "feature_guide": no dedicated documents_meta source_type exists for
alert-type explanations specifically (Phase 4 didn't author one), and "feature_guide" is the
closest conceptual bucket. This only affects citation labeling, not retrieval — `category` in
answer_kb_query() exists solely to trigger the PRICING gate, not to filter which documents are
searched (see app/kb/retrieve.py — retrieval always searches the whole collection).
"""

from chromadb.api.models.Collection import Collection

from app.llm.base import LLMProvider
from app.rag.pipeline import RAGResult, answer_kb_query


async def explain_feature(params: dict, *, llm: LLMProvider, kb_collection: Collection | None = None, **_) -> RAGResult:
    return await answer_kb_query(params.get("kb_topic", ""), "feature_guide", llm, collection=kb_collection)


async def explain_alert_type(
    params: dict, *, llm: LLMProvider, kb_collection: Collection | None = None, **_
) -> RAGResult:
    return await answer_kb_query(params.get("kb_topic", ""), "feature_guide", llm, collection=kb_collection)


async def app_faq(params: dict, *, llm: LLMProvider, kb_collection: Collection | None = None, **_) -> RAGResult:
    return await answer_kb_query(params.get("kb_topic", ""), "app_faq", llm, collection=kb_collection)


async def troubleshooting_device(
    params: dict, *, llm: LLMProvider, kb_collection: Collection | None = None, **_
) -> RAGResult:
    return await answer_kb_query(params.get("kb_topic", ""), "troubleshooting", llm, collection=kb_collection)


async def policy_question(params: dict, *, llm: LLMProvider, kb_collection: Collection | None = None, **_) -> RAGResult:
    return await answer_kb_query(params.get("kb_topic", ""), "policy", llm, collection=kb_collection)


async def pricing(params: dict, *, llm: LLMProvider, kb_collection: Collection | None = None, **_) -> RAGResult:
    return await answer_kb_query(params.get("kb_topic", ""), "pricing", llm, collection=kb_collection)
