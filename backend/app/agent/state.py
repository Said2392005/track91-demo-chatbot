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
    # popped (read-once) by entry_node; consumed by semantic_analysis_node via app.nlu.pipeline
    pending_clarification: dict | None

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
    missing_entity: str | None  # only set when route_outcome == CLARIFICATION_NEEDED

    # tool execution — set by gps_tool/mongo_tool/rag_tool node
    tool_result: Any

    # Dual-intent (Q2's "middle option") — set only when app.nlu.pipeline.analyze() detects a
    # real second intent on top of a cleanly-resolved primary (app/nlu/second_intent.py). None/
    # empty for the overwhelmingly common single-intent turn, which is otherwise unaffected.
    secondary_raw_intent: str | None
    secondary_entities: dict
    secondary_unresolved_required: list[str]
    secondary_ambiguous: dict
    secondary_route_outcome: str | None
    secondary_tool_name: str | None
    secondary_subsystem: str | None
    secondary_route_params: dict
    secondary_clarifying_question: str | None
    secondary_missing_entity: str | None
    secondary_tool_result: Any

    # synthesis — set by synthesis_node
    response_text: str
    citations: list[dict]
