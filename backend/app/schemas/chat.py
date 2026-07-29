from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    response: str
    intent: str | None = None
    citations: list[dict] = []


class ChatMessageOut(BaseModel):
    # ChatMessageRepository returns raw Mongo documents (extra fields like _id, session_id,
    # company_id, tool_called) — explicitly ignore rather than rely on pydantic's default.
    model_config = ConfigDict(extra="ignore")

    role: str
    content: str
    created_at: datetime
    intent: str | None = None


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatMessageOut]
