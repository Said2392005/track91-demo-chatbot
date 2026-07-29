"""
DeepSeek adapter — OpenAI-compatible chat completions HTTP API. Default cheap dev-model
provider per the roadmap's fixed tech stack. Request/response handling verified with a mocked
HTTP transport (tests/test_llm_provider.py) — not exercised against the live API by default in
this build (see app/llm/providers/groq.py for the free-tier alternative actually used for real
generation testing, since a DeepSeek key wasn't configured).
"""

from app.llm.providers.openai_compatible import OpenAICompatibleProvider


class DeepSeekProvider(OpenAICompatibleProvider):
    api_base = "https://api.deepseek.com"
    default_model = "deepseek-chat"
