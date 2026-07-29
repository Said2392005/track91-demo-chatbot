"""
Fallback provider used when the configured LLM provider can't actually be constructed (e.g. no
API key set) — lets the app start and serve every non-generation-dependent path (greeting,
clarifying questions, backlog-unsupported, out-of-scope, template responses) instead of
refusing to start entirely. Only the specific turns that need real generation
(RAG/GENERAL_KNOWLEDGE answers, LIVE_API/MONGO_REPO synthesis phrasing) fail, with a clear
error rather than a raw provider construction crash at import time.
"""

from app.llm.base import LLMProvider, LLMResponse, Message


class LLMUnavailableError(RuntimeError):
    pass


class UnavailableLLMProvider(LLMProvider):
    def __init__(self, reason: str = "No LLM provider is configured"):
        self._reason = reason

    async def generate(self, messages: list[Message], **kwargs) -> LLMResponse:
        raise LLMUnavailableError(self._reason)
