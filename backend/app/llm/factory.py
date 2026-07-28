from functools import lru_cache

from app.core.config import settings
from app.llm.base import LLMProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "deepseek":
        from app.llm.providers.deepseek import DeepSeekProvider

        return DeepSeekProvider(api_key=settings.deepseek_api_key)

    raise ValueError(f"Unknown llm_provider config value: {settings.llm_provider!r}")
