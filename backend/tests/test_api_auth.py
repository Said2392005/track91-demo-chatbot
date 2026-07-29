"""Contract tests for POST /auth/login."""

from datetime import datetime, timezone

from bson import ObjectId

from app.core.security import hash_password


async def _seed_user(db, *, email="jane@example.com", password="correct-horse", status="active"):
    company_id = ObjectId()
    await db.users.insert_one(
        {
            "company_id": company_id,
            "name": "Jane Fleet Manager",
            "email": email,
            "role": "fleet_manager",
            "status": status,
            "password_hash": hash_password(password),
            "created_at": datetime.now(timezone.utc),
        }
    )
    return company_id


async def test_login_success_returns_token(api_client, db):
    await _seed_user(db, email="login-success@example.com", password="correct-horse")

    response = await api_client.post("/auth/login", json={"email": "login-success@example.com", "password": "correct-horse"})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert body["access_token"]


async def test_login_wrong_password_is_401(api_client, db):
    await _seed_user(db, email="wrong-pw@example.com", password="correct-horse")

    response = await api_client.post("/auth/login", json={"email": "wrong-pw@example.com", "password": "wrong-password"})

    assert response.status_code == 401


async def test_login_unknown_email_is_401(api_client):
    response = await api_client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever"})
    assert response.status_code == 401


async def test_login_inactive_account_is_401(api_client, db):
    await _seed_user(db, email="inactive@example.com", password="correct-horse", status="disabled")

    response = await api_client.post("/auth/login", json={"email": "inactive@example.com", "password": "correct-horse"})

    assert response.status_code == 401


async def test_issued_token_authorizes_a_protected_route(api_client, db):
    """Round-trip: login -> use the token on /chat/{id}/history (any protected route) ->
    must not be rejected as unauthorized (a 404 for a made-up session_id is fine and expected;
    a 401 would mean the token didn't work)."""
    await _seed_user(db, email="round-trip@example.com", password="correct-horse")
    login = await api_client.post("/auth/login", json={"email": "round-trip@example.com", "password": "correct-horse"})
    token = login.json()["access_token"]

    response = await api_client.get(f"/chat/{ObjectId()}/history", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404  # session not found, not 401
