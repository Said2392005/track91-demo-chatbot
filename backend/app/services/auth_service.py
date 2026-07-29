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
        if not verify_password(password, user["password_hash"]):
            raise AuthError("Invalid email or password")
        if user.get("status") != "active":
            raise AuthError("Account is not active")

        return create_access_token(
            str(user["_id"]), str(user["company_id"]), user.get("role", "fleet_manager"), now=now
        )
