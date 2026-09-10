"""Cited generation — the LLM only phrases the final answer from already-assembled, already-
gated context (roadmap rule: the LLM never decides which system of record to hit, and here it
never sees content that hasn't already passed the PRICING gate)."""

from app.core.config import settings
from app.llm.base import LLMProvider, Message
from app.rag.context_assembler import AssembledContext

GENERATION_SYSTEM_PROMPT = (
    "You are Track91's fleet-management assistant. Answer using ONLY the provided context — "
    "never outside knowledge. Cite sources as [Source N] matching the context blocks. If the "
    "context doesn't answer the question, say so rather than guessing. If the question also "
    "asks about something the context has nothing to do with, silently ignore that part — no "
    "caveat, no apology, no offer to help with it. Answer confidently, as if that other part "
    "was never asked."
)


async def generate_cited_answer(query: str, context: AssembledContext, llm: LLMProvider) -> str:
    prompt = f"Context:\n{context.context_text}\n\nQuestion: {query}"
    response = await llm.generate(
        [
            Message(role="system", content=GENERATION_SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ],
        call_type="rag_generation",
        max_tokens=settings.llm_max_tokens,
    )
    return response.content
