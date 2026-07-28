"""
Graph state schema. All IDs are strings, not ObjectId — see serialization.py for why.
`total=False`: most fields are only present after the node that produces them has run.
"""

from datetime import datetime
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # input (set once, at graph invocation)
    utterance: str
    company_id: str
    session_id: str
    user_id: str
    now: datetime

    # memory (Phase 8) — fetched by entry_node
    active_entities: dict

    # semantic analysis (Phase 6) — set by semantic_analysis_node
    raw_intent: str
    final_intent: str
    entities: dict
    unresolved_required: list[str]
    ambiguous: dict

    # routing (Phase 9) — set by router_node
    route_outcome: str
    tool_name: str | None
    subsystem: str | None
    route_params: dict
    clarifying_question: str | None

    # tool execution — set by gps_tool/mongo_tool/rag_tool node
    tool_result: Any

    # synthesis — set by synthesis_node
    response_text: str
    citations: list[dict]
