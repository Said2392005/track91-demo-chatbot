"""
The deterministic intent-to-tool router — ADR 003
(docs/phase-2-architecture/adr/003-deterministic-intent-routing.md).

`route()` is pure and synchronous: given an already-classified intent (Phase 6), already-
extracted entities (Phase 6, which has already done its own coreference resolution against
active_entities), and `memory_state` (Phase 8's active entities), it decides which tool to call
and with what params — or that no tool should be called at all. No I/O, no LLM call, no
randomness — table-driven-testable by construction, matching the roadmap's Phase 9 test format:
(intent, entities, memory-state) -> (tool called, params passed).

`memory_state["active_entities"]` is consulted here too, as a defense-in-depth fill-in for a
required entity still missing from `entities` — on top of, not instead of, Phase 6's own
coreference resolution. Phase 6 handles the normal "pronoun present in this message, resolve it"
case; this is the routing-layer safety net for "still missing when we got here, for whatever
reason, check memory before giving up and asking a clarifying question."

Execution (actually calling a tool, which needs async I/O) is deliberately a separate function,
`execute_tool()` — keeping the decision pure is what makes it fast and easy to test exhaustively.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.taxonomy import INTENT_SPECS
from app.router.clarification import clarifying_question
from app.router.registry import TOOL_REGISTRY

Outcome = Literal["TOOL_CALL", "CLARIFICATION_NEEDED", "BACKLOG_UNSUPPORTED", "NO_TOOL", "UNKNOWN_INTENT"]

# Entity spec name (app/core/taxonomy.py) -> resolved-entities dict key (app/nlu/entity_extractor.py)
_ENTITY_KEY = {"vehicle_ref": "vehicle_id", "driver_ref": "driver_id", "geofence_ref": "geofence_id"}


def _key(entity_name: str) -> str:
    return _ENTITY_KEY.get(entity_name, entity_name)


@dataclass
class RouteDecision:
    outcome: Outcome
    intent: str
    tool_name: str | None = None
    subsystem: str | None = None
    params: dict = field(default_factory=dict)
    clarifying_question: str | None = None
    # The raw taxonomy requirement name (e.g. "vehicle_ref", "one_of:vehicle_ref|driver_ref")
    # that's still missing — set only when outcome is CLARIFICATION_NEEDED. Lets clarify_node
    # record exactly what the next turn needs to resolve to complete this intent (see
    # SessionRepository.set_pending_clarification).
    missing_entity: str | None = None


def route(intent: str, entities: dict, memory_state: dict | None = None) -> RouteDecision:
    spec = INTENT_SPECS.get(intent)
    if spec is None:
        return RouteDecision(outcome="UNKNOWN_INTENT", intent=intent)

    if spec.subsystem == "NONE":
        return RouteDecision(outcome="NO_TOOL", intent=intent)

    if not spec.mvp:
        return RouteDecision(outcome="BACKLOG_UNSUPPORTED", intent=intent)

    filled = dict(entities)
    active_entities = (memory_state or {}).get("active_entities") or {}
    for active_key in ("vehicle_id", "driver_id", "geofence_id"):
        if active_key not in filled and active_key in active_entities:
            filled[active_key] = active_entities[active_key]

    missing = [r for r in spec.required if _key(r) not in filled]
    if spec.required_one_of and not any(_key(r) in filled for r in spec.required_one_of):
        missing.append("one_of:" + "|".join(spec.required_one_of))

    if missing:
        return RouteDecision(
            outcome="CLARIFICATION_NEEDED",
            intent=intent,
            clarifying_question=clarifying_question(missing[0]),
            missing_entity=missing[0],
        )

    tool = TOOL_REGISTRY.get(intent)
    if tool is None:
        return RouteDecision(outcome="NO_TOOL", intent=intent)

    return RouteDecision(outcome="TOOL_CALL", intent=intent, tool_name=tool.name, subsystem=tool.subsystem, params=filled)


async def execute_tool(decision: RouteDecision, **kwargs) -> Any:
    if decision.outcome != "TOOL_CALL":
        raise ValueError(f"execute_tool() called on a non-TOOL_CALL decision: {decision.outcome!r}")
    tool = TOOL_REGISTRY[decision.intent]
    return await tool.handler(decision.params, **kwargs)
