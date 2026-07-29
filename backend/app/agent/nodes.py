"""
Graph nodes — Phase 10 assembles Phases 6-9 into a LangGraph graph; no new business logic
lives here beyond the ObjectId<->str boundary conversion state serialization requires
(serialization.py) and response phrasing/templating (response_synthesis.py, templates.py).

Side effects (Mongo writes, Fleet GPS/LLM API calls) live only inside the tool nodes
(gps_tool_node/mongo_tool_node/rag_tool_node) and memory_update_node, per the phase's stated
constraint. entry_node and semantic_analysis_node perform read-only Mongo lookups (entity
resolution — canonicalizing "MH12AB1234" to a vehicle_id, fetching active-entity state) as
inherent, already-established Phase 6/8 behavior, not new "tool calling"; they never write.
router_node, clarify_node stay fully pure (route() has no I/O at all, by ADR 003). synthesis_node
is the one documented exception: it calls the LLM to phrase raw LIVE_API/MONGO_REPO data into
natural language — not treated as a disallowed "side effect" here, since LLM-phrasing-only is
explicitly the LLM's designated job throughout this roadmap (never DB writes, never the Fleet
GPS API, and RAG/GENERAL_KNOWLEDGE paths already produced their final text during tool
execution, so synthesis_node makes at most one LLM call, only for the two raw-data subsystems).
"""

import dataclasses

from app.agent.response_synthesis import phrase_tool_result
from app.agent.serialization import entities_to_object_ids, sanitize_for_state, to_object_id
from app.agent.state import AgentState
from app.agent.templates import LLM_UNAVAILABLE_RESPONSE, direct_response
from app.llm.providers.unavailable import LLMUnavailableError
from app.memory.active_entity_tracker import get_active_entities, set_active_entity
from app.nlu.pipeline import analyze
from app.router.router import RouteDecision, execute_tool, route


def _decision_from_state(state: AgentState) -> RouteDecision:
    return RouteDecision(
        outcome=state["route_outcome"],
        intent=state["final_intent"],
        tool_name=state.get("tool_name"),
        subsystem=state.get("subsystem"),
        params=entities_to_object_ids(state.get("route_params", {})),
        clarifying_question=state.get("clarifying_question"),
    )


# Every field this graph produces per turn EXCEPT active_entities (Phase 8's cross-turn
# memory, by design) and the caller-supplied input fields. With a checkpointer attached,
# LangGraph does not reset state between separate ainvoke() calls on the same thread_id — any
# key a node doesn't explicitly overwrite this turn keeps its value from the PREVIOUS turn's
# checkpoint. Verified empirically, not assumed: a first version of this node without this
# reset left turn 2's tool_result holding turn 1's GPS data even when turn 2 correctly routed
# to CLARIFICATION_NEEDED and never ran a tool node at all (caught by
# tests/test_agent_graph_integration.py's active-entity-expiry scenario).
_PER_TURN_RESET = {
    "raw_intent": None,
    "final_intent": None,
    "entities": {},
    "unresolved_required": [],
    "ambiguous": {},
    "route_outcome": None,
    "tool_name": None,
    "subsystem": None,
    "route_params": {},
    "clarifying_question": None,
    "tool_result": None,
    "response_text": None,
    "citations": [],
}


def make_entry_node(session_repo):
    async def entry_node(state: AgentState) -> dict:
        active_entities = await get_active_entities(
            session_repo, to_object_id(state["company_id"]), to_object_id(state["session_id"]), now=state["now"]
        )
        return {**_PER_TURN_RESET, "active_entities": sanitize_for_state(active_entities)}

    return entry_node


def make_semantic_analysis_node(classifier, db):
    async def semantic_analysis_node(state: AgentState) -> dict:
        active_entities = entities_to_object_ids(state.get("active_entities", {}))
        result = await analyze(
            state["utterance"],
            classifier,
            to_object_id(state["company_id"]),
            db,
            session_state={"active_entities": active_entities},
            now=state["now"],
        )
        return {
            "raw_intent": result.raw_intent,
            "final_intent": result.final_intent,
            "entities": sanitize_for_state(result.entities),
            "unresolved_required": result.unresolved_required,
            "ambiguous": sanitize_for_state(result.ambiguous),
        }

    return semantic_analysis_node


def make_router_node():
    async def router_node(state: AgentState) -> dict:
        # Routes on raw_intent, not final_intent: Phase 6's pipeline.analyze() already
        # downgrades final_intent to "CLARIFICATION_NEEDED" when entities are unresolved, but
        # route() is designed to receive the original actionable intent (e.g.
        # "GET_VEHICLE_SPEED") and make that same determination itself — including its own
        # memory_state fallback, a superset of what Phase 6 already checked. Feeding it
        # final_intent="CLARIFICATION_NEEDED" instead looks like a NONE-subsystem meta intent
        # (app/core/taxonomy.py) and incorrectly resolves to NO_TOOL — caught by
        # tests/test_agent_graph_integration.py's active-entity-expiry scenario, not by
        # inspection. Phase 9's router is the authoritative "does this need clarification"
        # decision for actionable intents; Phase 6's final_intent/unresolved_required/ambiguous
        # remain in state as diagnostic output, not as what routing actually keys off of.
        decision = route(
            state["raw_intent"], state.get("entities", {}), {"active_entities": state.get("active_entities", {})}
        )
        return {
            "route_outcome": decision.outcome,
            "tool_name": decision.tool_name,
            "subsystem": decision.subsystem,
            "route_params": decision.params,
            "clarifying_question": decision.clarifying_question,
        }

    return router_node


def route_condition(state: AgentState) -> str:
    outcome = state["route_outcome"]
    if outcome == "CLARIFICATION_NEEDED":
        return "clarify"
    if outcome == "TOOL_CALL":
        subsystem = state["subsystem"]
        if subsystem == "LIVE_API":
            return "gps_tool"
        if subsystem == "MONGO_REPO":
            return "mongo_tool"
        if subsystem in ("RAG", "GENERAL_FALLBACK"):
            return "rag_tool"
    return "synthesis"  # NO_TOOL, BACKLOG_UNSUPPORTED, UNKNOWN_INTENT — nothing to call


def make_clarify_node():
    async def clarify_node(state: AgentState) -> dict:
        return {"response_text": state.get("clarifying_question") or "Could you clarify what you're asking about?"}

    return clarify_node


def make_gps_tool_node(gps_client):
    async def gps_tool_node(state: AgentState) -> dict:
        result = await execute_tool(_decision_from_state(state), gps_client=gps_client, now=state["now"])
        return {"tool_result": sanitize_for_state(result)}

    return gps_tool_node


def make_mongo_tool_node(db):
    async def mongo_tool_node(state: AgentState) -> dict:
        result = await execute_tool(
            _decision_from_state(state), company_id=to_object_id(state["company_id"]), db=db, now=state["now"]
        )
        return {"tool_result": sanitize_for_state(result)}

    return mongo_tool_node


def make_rag_tool_node(llm, kb_collection):
    async def rag_tool_node(state: AgentState) -> dict:
        # Caught here, not left to propagate: an unhandled LLMUnavailableError would abort the
        # graph before memory_update_node runs, silently losing an already-resolved entity
        # (e.g. an explicit vehicle_ref this turn) just because *generation* failed — found by
        # actually running the server end-to-end with no LLM configured, not by inspection. See
        # templates.LLM_UNAVAILABLE_RESPONSE's docstring for the full story.
        try:
            result = await execute_tool(_decision_from_state(state), llm=llm, kb_collection=kb_collection)
        except LLMUnavailableError:
            return {"tool_result": {"answer": LLM_UNAVAILABLE_RESPONSE, "citations": [], "llm_invoked": False}}
        # RAGResult (RAG subsystem) -> plain dict; GENERAL_KNOWLEDGE's handler already returns
        # a plain str. Both are already checkpoint-safe (no ObjectId/datetime involved), but
        # asdict() keeps the dataclass out of state for a uniform, plain-data shape.
        if dataclasses.is_dataclass(result):
            result = dataclasses.asdict(result)
        return {"tool_result": result}

    return rag_tool_node


def make_synthesis_node(llm):
    async def synthesis_node(state: AgentState) -> dict:
        outcome = state["route_outcome"]

        if outcome == "CLARIFICATION_NEEDED":
            return {}  # clarify_node already set response_text

        if outcome in ("NO_TOOL", "BACKLOG_UNSUPPORTED", "UNKNOWN_INTENT"):
            return {"response_text": direct_response(outcome, state.get("final_intent", ""))}

        tool_result = state.get("tool_result")
        subsystem = state.get("subsystem")

        if subsystem in ("RAG", "GENERAL_FALLBACK"):
            if isinstance(tool_result, dict) and "answer" in tool_result:
                return {"response_text": tool_result["answer"], "citations": tool_result.get("citations", [])}
            return {"response_text": str(tool_result)}

        # LIVE_API / MONGO_REPO: raw structured data, not yet natural language. Same
        # catch-inside-the-node reasoning as rag_tool_node above — must not abort the graph
        # before memory_update_node runs.
        try:
            text = await phrase_tool_result(state["utterance"], tool_result, llm)
        except LLMUnavailableError:
            text = LLM_UNAVAILABLE_RESPONSE
        return {"response_text": text}

    return synthesis_node


def make_memory_update_node(session_repo):
    async def memory_update_node(state: AgentState) -> dict:
        company_id = to_object_id(state["company_id"])
        session_id = to_object_id(state["session_id"])
        now = state["now"]

        await session_repo.touch(company_id, session_id, now)

        entities = state.get("entities", {})
        for entity_type, key in (("vehicle", "vehicle_id"), ("driver", "driver_id"), ("geofence", "geofence_id")):
            if entities.get(key):
                await set_active_entity(session_repo, company_id, session_id, entity_type, to_object_id(entities[key]), now)

        return {}

    return memory_update_node
