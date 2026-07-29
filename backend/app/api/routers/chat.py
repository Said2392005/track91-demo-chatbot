from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, get_chat_service, get_current_user
from app.api.object_id_param import parse_object_id
from app.core.logging import session_id_var
from app.schemas.chat import ChatHistoryResponse, ChatMessageOut, ChatRequest, ChatResponse
from app.services.chat_service import ChatService, SessionNotFoundError

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def send_message(
    body: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    session_object_id = parse_object_id(body.session_id, "session_id") if body.session_id else None
    try:
        result = await chat_service.handle_message(
            current_user.company_object_id, current_user.user_object_id, session_object_id, body.message
        )
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session_id_var.set(result["session_id"])
    return ChatResponse(**result)


@router.get("/{session_id}/history", response_model=ChatHistoryResponse)
async def get_history(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatHistoryResponse:
    session_object_id = parse_object_id(session_id, "session_id")
    session_id_var.set(session_id)
    try:
        messages = await chat_service.get_history(current_user.company_object_id, session_object_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return ChatHistoryResponse(session_id=session_id, messages=[ChatMessageOut(**m) for m in messages])
