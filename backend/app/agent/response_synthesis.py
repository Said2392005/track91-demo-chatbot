"""
Phrases raw tool data (LIVE_API/MONGO_REPO results — plain dicts/lists, not yet natural
language) into a final answer. RAG and GENERAL_KNOWLEDGE tool results are already
LLM-generated final text by the time they reach synthesis (Phase 7/9 do that generation as
part of tool execution itself) — this module is only for the two subsystems whose tools return
raw structured data instead.
"""

from app.core.config import settings
from app.llm.base import LLMProvider, Message

SYNTHESIS_SYSTEM_PROMPT = (
    "You are Track91's fleet-management assistant. Phrase the data below as a clear, natural "
    "answer — only use what's provided, never invent numbers or details. If it's empty or "
    "nothing was found, say so plainly. If the question also asks about something the data "
    "has nothing to do with, silently ignore that part — no caveat, no apology, no offer to "
    "help with it. Answer confidently, as if that other part was never asked."
)


async def phrase_tool_result(utterance: str, tool_result, llm: LLMProvider) -> str:
    prompt = f"User asked: {utterance}\n\nData retrieved: {tool_result}"
    response = await llm.generate(
        [
            Message(role="system", content=SYNTHESIS_SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ],
        call_type="response_synthesis",
        max_tokens=settings.llm_max_tokens,
    )
    return response.content
