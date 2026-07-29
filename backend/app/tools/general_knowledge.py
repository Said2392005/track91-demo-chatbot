"""
GENERAL_KNOWLEDGE handler — the one KB-adjacent intent with no ingested source document by
design (intent-taxonomy.md: "explicitly excluded from anything account-specific or
money-specific"). Answered by a direct LLM call, no ChromaDB retrieval and no PRICING-style
gate — there's no approved/unapproved distinction to enforce here, unlike PRICING, because this
intent is defined to never touch account-specific or money-specific content in the first place.
"""

from app.llm.base import LLMProvider, Message

GENERAL_KNOWLEDGE_SYSTEM_PROMPT = (
    "You are a helpful assistant for a fleet-management platform (Track91). The user is asking "
    "a general knowledge question that is not specific to Track91's product or account data "
    "(e.g. GPS/telematics terminology, industry standards). Answer briefly and accurately from "
    "general knowledge. Never state or imply anything about Track91's own pricing, a specific "
    "account's data, or any Track91-specific feature behavior — if the question turns out to "
    "need any of that, say you can't help with that particular part and suggest contacting "
    "support instead."
)


async def answer_general_knowledge(query: str, llm: LLMProvider) -> str:
    response = await llm.generate(
        [
            Message(role="system", content=GENERAL_KNOWLEDGE_SYSTEM_PROMPT),
            Message(role="user", content=query),
        ],
        call_type="general_knowledge",
    )
    return response.content


async def general_knowledge(params: dict, *, llm: LLMProvider, **_) -> str:
    """Tool-registry-shaped wrapper (uniform `(params, **kwargs)` signature) around
    answer_general_knowledge() above."""
    return await answer_general_knowledge(params.get("kb_topic", ""), llm)
