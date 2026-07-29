"""Contract tests for GET /usage/summary."""

from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.core.security import create_access_token


def _auth_header(company_id: ObjectId, user_id: ObjectId | None = None) -> dict:
    token, _ = create_access_token(str(user_id or ObjectId()), str(company_id), "fleet_manager")
    return {"Authorization": f"Bearer {token}"}


async def _insert_usage(db, company_id, prompt_tokens, completion_tokens, when, call_type="response_synthesis"):
    await db.llm_usage.insert_one(
        {
            "company_id": company_id,
            "user_id": ObjectId(),
            "session_id": ObjectId(),
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "call_type": call_type,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "created_at": when,
        }
    )


async def test_usage_summary_without_auth_is_401(api_client):
    now = datetime.now(timezone.utc)
    response = await api_client.get(
        "/usage/summary", params={"start": (now - timedelta(days=1)).isoformat(), "end": now.isoformat()}
    )
    assert response.status_code == 401


async def test_usage_summary_rejects_end_before_start(api_client):
    now = datetime.now(timezone.utc)
    response = await api_client.get(
        "/usage/summary",
        params={"start": now.isoformat(), "end": (now - timedelta(days=1)).isoformat()},
        headers=_auth_header(ObjectId()),
    )
    assert response.status_code == 400


async def test_usage_summary_sums_usage_for_the_caller_company(api_client, db):
    company_id = ObjectId()
    now = datetime.now(timezone.utc)
    await _insert_usage(db, company_id, 100, 20, now)
    await _insert_usage(db, company_id, 50, 10, now, call_type="rag_generation")

    response = await api_client.get(
        "/usage/summary",
        params={"start": (now - timedelta(hours=1)).isoformat(), "end": (now + timedelta(hours=1)).isoformat()},
        headers=_auth_header(company_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["call_count"] == 2
    assert body["prompt_tokens"] == 150
    assert body["completion_tokens"] == 30
    assert body["total_tokens"] == 180
    assert body["calls_missing_usage"] == 0


async def test_usage_summary_is_scoped_to_the_callers_company(api_client, db):
    own_company, other_company = ObjectId(), ObjectId()
    now = datetime.now(timezone.utc)
    await _insert_usage(db, own_company, 10, 5, now)
    await _insert_usage(db, other_company, 999, 999, now)

    response = await api_client.get(
        "/usage/summary",
        params={"start": (now - timedelta(hours=1)).isoformat(), "end": (now + timedelta(hours=1)).isoformat()},
        headers=_auth_header(own_company),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["call_count"] == 1
    assert body["prompt_tokens"] == 10


async def test_usage_summary_excludes_calls_outside_the_window(api_client, db):
    company_id = ObjectId()
    now = datetime.now(timezone.utc)
    await _insert_usage(db, company_id, 10, 5, now - timedelta(days=30))

    response = await api_client.get(
        "/usage/summary",
        params={"start": (now - timedelta(hours=1)).isoformat(), "end": (now + timedelta(hours=1)).isoformat()},
        headers=_auth_header(company_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["call_count"] == 0
    assert body["prompt_tokens"] == 0


async def test_usage_summary_reports_calls_missing_usage_data(api_client, db):
    company_id = ObjectId()
    now = datetime.now(timezone.utc)
    await _insert_usage(db, company_id, None, None, now)

    response = await api_client.get(
        "/usage/summary",
        params={"start": (now - timedelta(hours=1)).isoformat(), "end": (now + timedelta(hours=1)).isoformat()},
        headers=_auth_header(company_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["call_count"] == 1
    assert body["calls_missing_usage"] == 1
    assert body["prompt_tokens"] == 0
