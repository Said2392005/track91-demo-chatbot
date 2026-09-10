import logging
from functools import lru_cache

from botocore.exceptions import BotoCoreError

from app.core.config import settings
from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)


def _build_bedrock() -> LLMProvider:
    from app.llm.providers.bedrock import BedrockProvider

    return BedrockProvider(
        model_id=settings.bedrock_model_id,
        region=settings.bedrock_region,
        profile=settings.aws_profile,
    )


_BUILDERS = {"bedrock": _build_bedrock}


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
    except (ValueError, BotoCoreError) as e:
        # BotoCoreError alongside ValueError: boto3.Session(profile_name=...) (bedrock.py)
        # raises botocore.exceptions.ProfileNotFound immediately at construction — eagerly,
        # unlike the old boto3.client() call it replaced, which deferred all credential errors
        # to the first real API call. A misspelled/missing aws_profile must degrade to
        # UnavailableLLMProvider the same way a missing API key always has here, not crash app
        # startup entirely — found by actually triggering this path, not by inspection.
        logger.warning("LLM provider unavailable (%s) — falling back to UnavailableLLMProvider", e)
        return UnavailableLLMProvider(str(e))
