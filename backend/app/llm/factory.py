import logging
from functools import lru_cache

from app.core.config import settings
from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)


def _build_deepseek() -> LLMProvider:
    from app.llm.providers.deepseek import DeepSeekProvider

    return DeepSeekProvider(api_key=settings.deepseek_api_key)


def _build_groq() -> LLMProvider:
    from app.llm.providers.groq import GroqProvider

    return GroqProvider(api_key=settings.groq_api_key)


_BUILDERS = {"deepseek": _build_deepseek, "groq": _build_groq}


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Never raises — falls back to UnavailableLLMProvider if the configured provider can't be
    constructed (e.g. missing API key), so the app can still start and serve every path that
    doesn't need real generation. See app/llm/providers/unavailable.py."""
    from app.llm.providers.unavailable import UnavailableLLMProvider

    builder = _BUILDERS.get(settings.llm_provider)
    if builder is None:
        logger.warning("Unknown llm_provider config value: %r — falling back to UnavailableLLMProvider", settings.llm_provider)
        return UnavailableLLMProvider(f"Unknown llm_provider config value: {settings.llm_provider!r}")

    try:
        return builder()
    except ValueError as e:
        logger.warning("LLM provider unavailable (%s) — falling back to UnavailableLLMProvider", e)
        return UnavailableLLMProvider(str(e))
