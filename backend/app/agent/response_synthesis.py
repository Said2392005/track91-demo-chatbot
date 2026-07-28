"""
Phrases raw tool data (LIVE_API/MONGO_REPO results — plain dicts/lists, not yet natural
language) into a final answer. RAG and GENERAL_KNOWLEDGE tool results are already
LLM-generated final text by the time they reach synthesis (Phase 7/9 do that generation as
part of tool execution itself) — this module is only for the two subsystems whose tools return
raw structured data instead.
"""

from app.llm.base import LLMProvider, Message

SYNTHESIS_SYSTEM_PROMPT = (
    "You are a helpful assistant for a fleet-management platform (Track91). You've just "
    "retrieved data to answer the user's question. Phrase it as a clear, concise, natural "
    "answer. Only use the data provided — never invent numbers or details not present in it. "
    "If the data is an empty list or indicates nothing was found, say so plainly."
)


async def phrase_tool_result(utterance: str, tool_result, llm: LLMProvider) -> str:
    prompt = f"User asked: {utterance}\n\nData retrieved: {tool_result}"
    response = await llm.generate(
        [
            Message(role="system", content=SYNTHESIS_SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ]
    )
    return response.content
