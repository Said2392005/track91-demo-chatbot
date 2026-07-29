"""Password hashing (bcrypt) and JWT issuing/verification for Phase 11 auth."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


class InvalidTokenError(Exception):
    pass


def create_access_token(user_id: str, company_id: str, role: str, now: datetime | None = None) -> tuple[str, int]:
    now = now or datetime.now(timezone.utc)
    expires_in = settings.jwt_expiry_minutes * 60
    payload = {
        "sub": user_id,
        "company_id": company_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as e:
        raise InvalidTokenError(str(e)) from e
