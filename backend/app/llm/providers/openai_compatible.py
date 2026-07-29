"""
Shared HTTP logic for OpenAI-compatible chat-completions APIs. DeepSeek and Groq both expose
the identical `/chat/completions` request/response shape (Groq's OpenAI-compatibility is
exactly why it was picked as a free-tier alternative to DeepSeek — see docs/phase-12-testing/
testing.md) — extracted here once a second real concrete adapter needed the exact same request-
building/response-parsing code, not speculatively ahead of that need. A concrete adapter only
supplies its own `api_base` and `default_model` (deepseek.py, groq.py).
"""

import httpx

from app.llm.base import LLMProvider, LLMResponse, Message, TokenUsage


def _parse_usage(data: dict) -> TokenUsage | None:
    # OpenAI-compatible shape: {"usage": {"prompt_tokens": N, "completion_tokens": N, ...}} —
    # confirmed against a real live Groq response, not assumed from the spec alone. Missing
    # entirely, or missing one of the two counts, is treated the same way: no usage data, not
    # a crash and not a guessed 0 (a provider that omits the field is different from one that
    # genuinely used 0 tokens).
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    if prompt_tokens is None and completion_tokens is None:
        return None
    return TokenUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


class OpenAICompatibleProvider(LLMProvider):
    api_base: str = ""
    default_model: str = ""

    def __init__(self, api_key: str, model: str | None = None, client: httpx.AsyncClient | None = None):
        if not api_key:
            raise ValueError(f"{type(self).__name__} requires a non-empty api_key")
        self._api_key = api_key
        self._model = model or self.default_model
        self._client = client or httpx.AsyncClient(base_url=self.api_base, timeout=30.0)

    async def generate(self, messages: list[Message], **kwargs) -> LLMResponse:
        response = await self._client.post(
            "/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "temperature": kwargs.get("temperature", 0.2),
                "max_tokens": kwargs.get("max_tokens", 512),
            },
        )
        response.raise_for_status()
        data = response.json()
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", self._model),
            raw=data,
            usage=_parse_usage(data),
        )
