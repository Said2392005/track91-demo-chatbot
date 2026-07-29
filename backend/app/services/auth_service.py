import asyncio
from datetime import datetime, timezone

from app.core.security import create_access_token, verify_password
from app.db.repositories.user_repository import UserRepository


class AuthError(Exception):
    pass


class AuthService:
    def __init__(self, user_repo: UserRepository):
        self._user_repo = user_repo

    async def login(self, email: str, password: str, now: datetime | None = None) -> tuple[str, int]:
        now = now or datetime.now(timezone.utc)
        user = await self._user_repo.find_by_email(email)
        if user is None or not user.get("password_hash"):
            raise AuthError("Invalid email or password")

        # bcrypt is deliberately CPU-slow (that's the point of it) and, critically, synchronous
        # — calling it directly here blocks the single asyncio event loop for its full duration,
        # serializing every concurrent login behind it rather than running them in parallel.
        # Found by Phase 12's load test: median /auth/login latency was 5.2s (max 7.8s) under
        # just 10 concurrent users, growing with each additional queued request — a textbook
        # blocking-call-in-an-async-handler bug, not bcrypt itself being slow. asyncio.to_thread
        # offloads the hash computation to a worker thread so the event loop stays free.
        password_ok = await asyncio.to_thread(verify_password, password, user["password_hash"])
        if not password_ok:
            raise AuthError("Invalid email or password")
        if user.get("status") != "active":
            raise AuthError("Account is not active")

        return create_access_token(
            str(user["_id"]), str(user["company_id"]), user.get("role", "fleet_manager"), now=now
        )
