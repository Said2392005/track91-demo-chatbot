from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.db.repositories.llm_usage_repository import LLMUsageRepository


async def test_record_then_summarize(db):
    repo = LLMUsageRepository(db)
    company_id, user_id, session_id = ObjectId(), ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)

    await repo.record(company_id, user_id, session_id, "groq", "llama-3.3-70b-versatile", "response_synthesis", 100, 20, now)
    await repo.record(company_id, user_id, session_id, "groq", "llama-3.3-70b-versatile", "rag_generation", 50, 10, now)

    summary = await repo.summarize(company_id, now - timedelta(minutes=1), now + timedelta(minutes=1))
    assert summary["call_count"] == 2
    assert summary["prompt_tokens"] == 150
    assert summary["completion_tokens"] == 30
    assert summary["calls_missing_usage"] == 0


async def test_summarize_counts_but_does_not_estimate_calls_with_no_usage_data(db):
    repo = LLMUsageRepository(db)
    company_id, user_id, session_id = ObjectId(), ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)

    await repo.record(company_id, user_id, session_id, "ollama", "llama3", "response_synthesis", None, None, now)
    await repo.record(company_id, user_id, session_id, "groq", "llama-3.3-70b-versatile", "rag_generation", 50, 10, now)

    summary = await repo.summarize(company_id, now - timedelta(minutes=1), now + timedelta(minutes=1))
    assert summary["call_count"] == 2
    assert summary["prompt_tokens"] == 50  # the None row contributes 0, not an estimate
    assert summary["completion_tokens"] == 10
    assert summary["calls_missing_usage"] == 1


async def test_summarize_excludes_calls_outside_the_time_window(db):
    repo = LLMUsageRepository(db)
    company_id, user_id, session_id = ObjectId(), ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)

    await repo.record(company_id, user_id, session_id, "groq", "llama-3.3-70b-versatile", "response_synthesis", 100, 20, now - timedelta(days=2))
    await repo.record(company_id, user_id, session_id, "groq", "llama-3.3-70b-versatile", "response_synthesis", 5, 5, now)

    summary = await repo.summarize(company_id, now - timedelta(hours=1), now + timedelta(hours=1))
    assert summary["call_count"] == 1
    assert summary["prompt_tokens"] == 5


async def test_summarize_scoped_to_company(db):
    repo = LLMUsageRepository(db)
    company_a, company_b = ObjectId(), ObjectId()
    user_id, session_id = ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)

    await repo.record(company_a, user_id, session_id, "groq", "llama-3.3-70b-versatile", "response_synthesis", 100, 20, now)
    await repo.record(company_b, user_id, session_id, "groq", "llama-3.3-70b-versatile", "response_synthesis", 999, 999, now)

    summary = await repo.summarize(company_a, now - timedelta(minutes=1), now + timedelta(minutes=1))
    assert summary["call_count"] == 1
    assert summary["prompt_tokens"] == 100


async def test_summarize_for_company_with_no_usage_returns_zeros(db):
    repo = LLMUsageRepository(db)
    now = datetime.now(timezone.utc)
    summary = await repo.summarize(ObjectId(), now - timedelta(hours=1), now + timedelta(hours=1))
    assert summary == {"call_count": 0, "prompt_tokens": 0, "completion_tokens": 0, "calls_missing_usage": 0}
