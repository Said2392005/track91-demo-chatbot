"""Cited generation — the LLM only phrases the final answer from already-assembled, already-
gated context (roadmap rule: the LLM never decides which system of record to hit, and here it
never sees content that hasn't already passed the PRICING gate)."""

from app.llm.base import LLMProvider, Message
from app.rag.context_assembler import AssembledContext

GENERATION_SYSTEM_PROMPT = (
    "You are a helpful assistant for a fleet-management platform (Track91). Answer the user's "
    "question using ONLY the provided context — never use outside knowledge. Cite sources "
    "using [Source N] notation matching the context blocks. If the context does not actually "
    "answer the question, say you don't have that information rather than guessing."
)


async def generate_cited_answer(query: str, context: AssembledContext, llm: LLMProvider) -> str:
    prompt = f"Context:\n{context.context_text}\n\nQuestion: {query}"
    response = await llm.generate(
        [
            Message(role="system", content=GENERATION_SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ],
        call_type="rag_generation",
    )
    return response.content
