"""
Chat orchestration: ensure a session exists, invoke the agent graph (Phase 10), persist the
turn, return a response DTO. Tenant isolation for session access falls straight out of
SessionRepository.get() being company_id-scoped (ADR 004) — a session_id belonging to another
company simply isn't found, which this service turns into SessionNotFoundError -> 404, with no
separate cross-tenant check needed here.

The LLMUnavailableError catch here is a defensive backstop, not the primary handling — Phase
10's rag_tool_node/synthesis_node (app/agent/nodes.py) catch it internally so a generation
failure degrades gracefully without aborting the graph before memory_update_node runs. This
catch exists in case some future node path forgets to.
"""

import logging
from datetime import datetime, timezone

from bson import ObjectId

from app.agent.templates import LLM_UNAVAILABLE_RESPONSE
from app.db.repositories.chat_message_repository import ChatMessageRepository
from app.db.repositories.session_repository import SessionRepository
from app.llm.providers.unavailable import LLMUnavailableError
from app.llm.usage_context import llm_call_identity

logger = logging.getLogger(__name__)


class ChatServiceError(Exception):
    pass


class SessionNotFoundError(ChatServiceError):
    pass


class ChatService:
    def __init__(self, graph, session_repo: SessionRepository, message_repo: ChatMessageRepository):
        self._graph = graph
        self._session_repo = session_repo
        self._message_repo = message_repo

    async def handle_message(
        self,
        company_id: ObjectId,
        user_id: ObjectId,
        session_id: ObjectId | None,
        message: str,
        now: datetime | None = None,
    ) -> dict:
        now = now or datetime.now(timezone.utc)

        if session_id is None:
            session = await self._session_repo.create(company_id, user_id, now)
            session_id = session["_id"]
        elif await self._session_repo.get(company_id, session_id) is None:
            raise SessionNotFoundError(f"Session {session_id} not found")

        config = {"configurable": {"thread_id": str(session_id)}}
        try:
            with llm_call_identity(company_id, user_id, session_id):
                result = await self._graph.ainvoke(
                    {"utterance": message, "company_id": str(company_id), "session_id": str(session_id), "now": now},
                    config=config,
                )
            response_text = result.get("response_text") or ""
            intent = result.get("final_intent")
            tool_called = result.get("tool_name")
            citations = result.get("citations", [])
        except LLMUnavailableError:
            logger.warning("LLM unavailable for session=%s — returning degraded response", session_id)
            response_text = LLM_UNAVAILABLE_RESPONSE
            intent, tool_called, citations = None, None, []

        await self._message_repo.insert(company_id, session_id, "user", message, now)
        await self._message_repo.insert(
            company_id, session_id, "assistant", response_text, now, intent=intent, tool_called=tool_called
        )

        return {"session_id": str(session_id), "response": response_text, "intent": intent, "citations": citations}

    async def get_history(self, company_id: ObjectId, session_id: ObjectId) -> list[dict]:
        if await self._session_repo.get(company_id, session_id) is None:
            raise SessionNotFoundError(f"Session {session_id} not found")
        return await self._message_repo.list_for_session(company_id, session_id)
