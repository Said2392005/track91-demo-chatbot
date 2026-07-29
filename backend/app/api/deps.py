"""
DI dependency providers. `get_db` and `get_graph` are the two roots — every other dependency
in this file builds on them via `Depends()`, which is what makes them cleanly overridable in
tests: `app.dependency_overrides[get_db] = lambda: fake_db` (or `get_graph`) cascades through
the whole tree without needing to override every individual service/repo dependency.
"""

from bson import ObjectId
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import InvalidTokenError, decode_access_token
from app.db.repositories.chat_message_repository import ChatMessageRepository
from app.db.repositories.llm_usage_repository import LLMUsageRepository
from app.db.repositories.session_repository import SessionRepository
from app.db.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService

_bearer_scheme = HTTPBearer(auto_error=False)


def get_db(request: Request) -> AsyncIOMotorDatabase:
    return request.app.state.db


def get_graph(request: Request):
    return request.app.state.graph


def get_user_repo(db: AsyncIOMotorDatabase = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_session_repo(db: AsyncIOMotorDatabase = Depends(get_db)) -> SessionRepository:
    return SessionRepository(db)


def get_message_repo(db: AsyncIOMotorDatabase = Depends(get_db)) -> ChatMessageRepository:
    return ChatMessageRepository(db)


def get_llm_usage_repo(db: AsyncIOMotorDatabase = Depends(get_db)) -> LLMUsageRepository:
    return LLMUsageRepository(db)


def get_auth_service(user_repo: UserRepository = Depends(get_user_repo)) -> AuthService:
    return AuthService(user_repo)


def get_chat_service(
    graph=Depends(get_graph),
    session_repo: SessionRepository = Depends(get_session_repo),
    message_repo: ChatMessageRepository = Depends(get_message_repo),
) -> ChatService:
    return ChatService(graph, session_repo, message_repo)


class CurrentUser:
    """company_id here is always derived from the verified JWT, never from a client-supplied
    request field — the source of truth ADR 004 requires for repository-layer tenant scoping."""

    def __init__(self, user_id: str, company_id: str, role: str):
        self.user_id = user_id
        self.company_id = company_id
        self.role = role

    @property
    def user_object_id(self) -> ObjectId:
        return ObjectId(self.user_id)

    @property
    def company_object_id(self) -> ObjectId:
        return ObjectId(self.company_id)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return CurrentUser(user_id=payload["sub"], company_id=payload["company_id"], role=payload.get("role", ""))
