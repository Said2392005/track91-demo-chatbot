"""
GENERAL_KNOWLEDGE handler — the one KB-adjacent intent with no ingested source document by
design (intent-taxonomy.md: "explicitly excluded from anything account-specific or
money-specific"). Answered by a direct LLM call, no ChromaDB retrieval and no PRICING-style
gate — there's no approved/unapproved distinction to enforce here, unlike PRICING, because this
intent is defined to never touch account-specific or money-specific content in the first place.
"""

from app.core.config import settings
from app.llm.base import LLMProvider, Message

GENERAL_KNOWLEDGE_SYSTEM_PROMPT = (
    "You are Track91's fleet-management assistant. The user is asking a general-knowledge "
    "question unrelated to Track91's own product/account data (e.g. GPS/telematics terms, "
    "industry standards) — answer briefly and accurately from general knowledge. Never state "
    "or imply anything about Track91's pricing, account data, or feature behavior; if this "
    "part needs that, say you can't help with that detail and suggest contacting support. If "
    "the question also asks about something unrelated to general knowledge (e.g. their own "
    "live fleet data), silently ignore that part — no caveat, no apology, no offer to help. "
    "Answer confidently, as if that other part was never asked."
)



async def answer_general_knowledge(query: str, llm: LLMProvider) -> str:
    response = await llm.generate(
        [
            Message(role="system", content=GENERAL_KNOWLEDGE_SYSTEM_PROMPT),
            Message(role="user", content=query),
        ],
        call_type="general_knowledge",
        max_tokens=settings.llm_max_tokens,
    )
    return response.content


async def general_knowledge(params: dict, *, llm: LLMProvider, **_) -> str:
    """Tool-registry-shaped wrapper (uniform `(params, **kwargs)` signature) around
    answer_general_knowledge() above."""
    return await answer_general_knowledge(params.get("kb_topic", ""), llm)
