"""
Wraps any LLMProvider to record token usage per call — installed once, at app assembly time
(app/main.py), around whatever concrete provider app.llm.factory.get_llm_provider() built, so
every real call site (intent classification, response synthesis, RAG generation, general
knowledge — see each module's `call_type=` kwarg on its llm.generate() call) is tracked
identically without any of them needing to know tracking exists.

Recording must never be able to break the actual LLM call it's piggybacking on: a Mongo write
failing here is a monitoring gap, not a reason to fail a chat turn that otherwise succeeded.
"""

import logging
from datetime import datetime, timezone

from app.db.repositories.llm_usage_repository import LLMUsageRepository
from app.llm.base import LLMProvider, LLMResponse, Message
from app.llm.usage_context import llm_call_identity_var

logger = logging.getLogger(__name__)


class TrackingLLMProvider(LLMProvider):
    def __init__(self, inner: LLMProvider, usage_repo: LLMUsageRepository, provider_name: str):
        self._inner = inner
        self._usage_repo = usage_repo
        self._provider_name = provider_name

    async def generate(self, messages: list[Message], **kwargs) -> LLMResponse:
        call_type = kwargs.pop("call_type", "unknown")
        response = await self._inner.generate(messages, **kwargs)
        await self._record(response, call_type)
        return response

    async def _record(self, response: LLMResponse, call_type: str) -> None:
        identity = llm_call_identity_var.get()
        if identity is None:
            # Shouldn't happen in real request handling (ChatService.handle_message sets this
            # before invoking the graph) — a direct/test call to a wrapped provider outside
            # that context has nothing to attribute usage to. Skip, don't guess or crash.
            logger.warning("LLM call with no ambient identity set — usage not recorded (call_type=%s)", call_type)
            return

        try:
            await self._usage_repo.record(
                company_id=identity.company_id,
                user_id=identity.user_id,
                session_id=identity.session_id,
                provider=self._provider_name,
                model=response.model,
                call_type=call_type,
                prompt_tokens=response.usage.prompt_tokens if response.usage else None,
                completion_tokens=response.usage.completion_tokens if response.usage else None,
                now=datetime.now(timezone.utc),
            )
        except Exception:
            logger.exception("failed to record LLM usage (call_type=%s) — chat response unaffected", call_type)
