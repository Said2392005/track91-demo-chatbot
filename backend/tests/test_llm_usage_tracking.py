"""
TrackingLLMProvider tests. Two scenarios required by this feature's spec:
1. A normal call with real token counts (a fake inner provider standing in for a real
   provider's parsed response shape — already verified against real live Bedrock/Groq calls in
   test_bedrock_provider.py and the OpenAI-compatible usage-parsing tests; a real end-to-end
   call through the tracking wrapper is exercised opt-in in tests/test_max_tokens_real_bedrock.py,
   gated on AWS credentials being resolvable, per this suite's "no live API calls by default"
   policy).
2. A provider that returns no token data at all (FakeLLMProvider, usage=None by default) —
   must record gracefully, not crash.
"""

from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.db.repositories.llm_usage_repository import LLMUsageRepository
from app.llm.base import LLMResponse, Message, TokenUsage
from app.llm.providers.fake import FakeLLMProvider
from app.llm.usage_context import llm_call_identity
from app.llm.usage_tracking import TrackingLLMProvider


class _FixedUsageProvider:
    """A minimal LLMProvider double that reports real, fixed token counts — standing in for a
    real OpenAI-compatible provider's parsed response without needing network access."""

    def __init__(self, prompt_tokens: int, completion_tokens: int, model: str = "openai.gpt-oss-120b-1:0"):
        self._usage = TokenUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        self._model = model

    async def generate(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(content="an answer", model=self._model, usage=self._usage)


async def test_normal_call_with_real_token_counts_is_recorded(db):
    usage_repo = LLMUsageRepository(db)
    tracked = TrackingLLMProvider(_FixedUsageProvider(prompt_tokens=42, completion_tokens=8), usage_repo, provider_name="bedrock")

    company_id, user_id, session_id = ObjectId(), ObjectId(), ObjectId()
    with llm_call_identity(company_id, user_id, session_id):
        response = await tracked.generate([Message(role="user", content="hi")], call_type="response_synthesis")

    assert response.content == "an answer"  # the wrapper must not alter the real response

    now = datetime.now(timezone.utc)
    summary = await usage_repo.summarize(company_id, now - timedelta(minutes=1), now + timedelta(minutes=1))
    assert summary["call_count"] == 1
    assert summary["prompt_tokens"] == 42
    assert summary["completion_tokens"] == 8
    assert summary["calls_missing_usage"] == 0

    raw = await db.llm_usage.find_one({"company_id": company_id})
    assert raw["provider"] == "bedrock"
    assert raw["model"] == "openai.gpt-oss-120b-1:0"
    assert raw["call_type"] == "response_synthesis"
    assert raw["user_id"] == user_id
    assert raw["session_id"] == session_id


async def test_provider_with_no_token_data_is_recorded_gracefully_not_crashed(db):
    """FakeLLMProvider never sets `usage` — the same shape a local Ollama deployment would
    produce. Must still record (with null counts), must not raise."""
    usage_repo = LLMUsageRepository(db)
    tracked = TrackingLLMProvider(FakeLLMProvider(canned_response="an answer"), usage_repo, provider_name="ollama")

    company_id, user_id, session_id = ObjectId(), ObjectId(), ObjectId()
    with llm_call_identity(company_id, user_id, session_id):
        response = await tracked.generate([Message(role="user", content="hi")], call_type="general_knowledge")

    assert response.content == "an answer"

    raw = await db.llm_usage.find_one({"company_id": company_id})
    assert raw is not None
    assert raw["provider"] == "ollama"
    assert raw["prompt_tokens"] is None
    assert raw["completion_tokens"] is None

    now = datetime.now(timezone.utc)
    summary = await usage_repo.summarize(company_id, now - timedelta(minutes=1), now + timedelta(minutes=1))
    assert summary["call_count"] == 1
    assert summary["calls_missing_usage"] == 1
    assert summary["prompt_tokens"] == 0
    assert summary["completion_tokens"] == 0


async def test_call_with_no_ambient_identity_set_does_not_crash(db):
    """A direct call to a wrapped provider outside ChatService.handle_message's context (e.g.
    a stray test, or a future call site that forgets to set identity) has nothing to attribute
    usage to — must skip recording, not raise, and the underlying call must still succeed."""
    usage_repo = LLMUsageRepository(db)
    tracked = TrackingLLMProvider(FakeLLMProvider(canned_response="an answer"), usage_repo, provider_name="bedrock")

    # db is a session-scoped fixture shared across this whole test file, so other tests' rows
    # are already present — compare a before/after delta rather than an absolute count.
    before = await db.llm_usage.count_documents({})
    response = await tracked.generate([Message(role="user", content="hi")], call_type="response_synthesis")
    after = await db.llm_usage.count_documents({})

    assert response.content == "an answer"
    assert after == before


async def test_call_type_kwarg_is_not_forwarded_to_the_inner_provider(db):
    """call_type is consumed by the wrapper, not leaked into the wrapped provider's own
    generate() kwargs (which, for a real OpenAI-compatible provider, only reads
    temperature/max_tokens and would otherwise silently ignore it — but it shouldn't be there
    at all)."""
    received_kwargs = {}

    class _SpyProvider:
        async def generate(self, messages, **kwargs) -> LLMResponse:
            received_kwargs.update(kwargs)
            return LLMResponse(content="ok", model="spy-model")

    usage_repo = LLMUsageRepository(db)
    tracked = TrackingLLMProvider(_SpyProvider(), usage_repo, provider_name="bedrock")

    with llm_call_identity(ObjectId(), ObjectId(), ObjectId()):
        await tracked.generate([Message(role="user", content="hi")], call_type="rag_generation", temperature=0.5)

    assert "call_type" not in received_kwargs
    assert received_kwargs["temperature"] == 0.5
