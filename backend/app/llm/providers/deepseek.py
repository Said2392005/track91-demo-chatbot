"""
DeepSeek adapter — OpenAI-compatible chat completions HTTP API. Default cheap dev-model
provider per the roadmap's fixed tech stack. Requires DEEPSEEK_API_KEY; not exercised against
the live API in this build (no credentials configured in this environment) — request/response
handling is verified with a mocked HTTP transport instead (tests/test_llm_provider.py).
"""

import httpx

from app.llm.base import LLMProvider, LLMResponse, Message

DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


class DeepSeekProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, client: httpx.AsyncClient | None = None):
        if not api_key:
            raise ValueError("DeepSeekProvider requires a non-empty api_key")
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient(base_url=DEEPSEEK_API_BASE, timeout=30.0)

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
        )
