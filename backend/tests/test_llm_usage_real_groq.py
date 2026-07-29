"""
A real, live call to Groq's actual API, through the full TrackingLLMProvider wrapper down to a
real Mongo write — not mocked, per this feature's explicit spec ("a normal Groq call with real
counts"). Opt-in on GROQ_API_KEY being configured (it is, in this environment's .env), skipped
otherwise — consistent with test_llm_provider.py's documented policy of no live API calls by
default so the suite still passes for anyone without a key. The response shape itself
(`usage.prompt_tokens`/`completion_tokens`) was confirmed against a real live Groq call before
writing app/llm/providers/openai_compatible.py's parsing logic, not assumed from the OpenAI spec
alone.
"""

from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from app.core.config import settings
from app.db.repositories.llm_usage_repository import LLMUsageRepository
from app.llm.base import Message
from app.llm.providers.groq import GroqProvider
from app.llm.usage_context import llm_call_identity
from app.llm.usage_tracking import TrackingLLMProvider

pytestmark = pytest.mark.skipif(
    not settings.groq_api_key, reason="GROQ_API_KEY not configured — real-provider tests are opt-in"
)


async def test_real_groq_call_records_real_token_counts(db):
    usage_repo = LLMUsageRepository(db)
    tracked = TrackingLLMProvider(GroqProvider(api_key=settings.groq_api_key), usage_repo, provider_name="groq")

    company_id, user_id, session_id = ObjectId(), ObjectId(), ObjectId()
    with llm_call_identity(company_id, user_id, session_id):
        response = await tracked.generate(
            [Message(role="user", content="Reply with exactly one word: hello")],
            call_type="response_synthesis",
        )

    assert response.content
    assert response.usage is not None
    assert response.usage.prompt_tokens > 0
    assert response.usage.completion_tokens > 0

    now = datetime.now(timezone.utc)
    summary = await usage_repo.summarize(company_id, now - timedelta(minutes=1), now + timedelta(minutes=1))
    assert summary["call_count"] == 1
    assert summary["calls_missing_usage"] == 0
    assert summary["prompt_tokens"] == response.usage.prompt_tokens
    assert summary["completion_tokens"] == response.usage.completion_tokens
