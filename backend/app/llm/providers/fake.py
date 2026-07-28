"""
Deterministic test double for LLMProvider — not a runtime provider option. Used to test code
that depends on the LLMProvider interface (e.g. the Phase 6 LLM-based intent classifier)
without a live API key or network access.
"""

from app.llm.base import LLMProvider, LLMResponse, Message


class FakeLLMProvider(LLMProvider):
    def __init__(self, canned_response: str | list[str] = ""):
        self._responses = [canned_response] if isinstance(canned_response, str) else list(canned_response)
        self._call_count = 0
        self.received_calls: list[list[Message]] = []

    async def generate(self, messages: list[Message], **kwargs) -> LLMResponse:
        self.received_calls.append(messages)
        content = self._responses[min(self._call_count, len(self._responses) - 1)]
        self._call_count += 1
        return LLMResponse(content=content, model="fake-model")
