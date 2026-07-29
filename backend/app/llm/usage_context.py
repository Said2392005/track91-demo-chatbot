"""
Ambient per-turn identity for LLM usage tracking (app/llm/usage_tracking.py) — the same
contextvars pattern app/core/logging.py already uses for request_id/session_id correlation,
applied here for the same reason: company_id/user_id/session_id are known once, at the top of
ChatService.handle_message(), but the actual llm.generate() calls happen 3-4 layers deeper
(e.g. rag_tool_node -> execute_tool -> kb_tools.pricing -> answer_kb_query ->
generate_cited_answer) through functions whose own job has nothing to do with who's asking —
threading three extra parameters through every one of those signatures for a cross-cutting
concern is exactly what this codebase already avoids for request_id/session_id logging.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from bson import ObjectId


@dataclass(frozen=True)
class LLMCallIdentity:
    company_id: ObjectId
    user_id: ObjectId
    session_id: ObjectId


llm_call_identity_var: ContextVar[LLMCallIdentity | None] = ContextVar("llm_call_identity", default=None)


@contextmanager
def llm_call_identity(company_id: ObjectId, user_id: ObjectId, session_id: ObjectId):
    token = llm_call_identity_var.set(LLMCallIdentity(company_id, user_id, session_id))
    try:
        yield
    finally:
        llm_call_identity_var.reset(token)
