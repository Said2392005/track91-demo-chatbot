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
from app.nlu import coreference
from app.nlu.pipeline import analyze
from app.router.router import RouteDecision, execute_tool, route


def _decision_from_state(state: AgentState) -> RouteDecision:
    # raw_intent, not final_intent: route_outcome/tool_name/subsystem/route_params (router_node,
    # below) were all computed by calling route(state["raw_intent"], ...) — final_intent is a
    # separate, Phase-6-only decision that can legitimately disagree with route_outcome. Real
    # bug, found live: route() fills a missing vehicle_ref from active_entities unconditionally
    # (defense-in-depth), but Phase 6's own coreference fill only fires when the utterance
    # contains a recognized pronoun (app/nlu/coreference.py — "my" isn't one). So "where is my
    # vehicle" (no pronoun, no explicit plate), asked again in a session with an active vehicle,
    # produced final_intent="CLARIFICATION_NEEDED" (Phase 6 didn't fill it) while
    # route_outcome="TOOL_CALL" (Phase 9 did) — using final_intent here looked up
    # TOOL_REGISTRY["CLARIFICATION_NEEDED"] and crashed with a KeyError instead of running the
    # tool route() had actually decided on.
    return RouteDecision(
        outcome=state["route_outcome"],
        intent=state["raw_intent"],
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
    "missing_entity": None,
    "tool_result": None,
    "secondary_raw_intent": None,
    "secondary_entities": {},
    "secondary_unresolved_required": [],
    "secondary_ambiguous": {},
    "secondary_route_outcome": None,
    "secondary_tool_name": None,
    "secondary_subsystem": None,
    "secondary_route_params": {},
    "secondary_clarifying_question": None,
    "secondary_missing_entity": None,
    "secondary_tool_result": None,
    "response_text": None,
    "citations": [],
}


def make_entry_node(session_repo):
    async def entry_node(state: AgentState) -> dict:
        company_id = to_object_id(state["company_id"])
        session_id = to_object_id(state["session_id"])
        active_entities = await get_active_entities(session_repo, company_id, session_id, now=state["now"])
        # Read-once: pop_pending_clarification clears it in the same op, so it can only ever
        # affect this one turn — see SessionRepository.pop_pending_clarification.
        pending_clarification = await session_repo.pop_pending_clarification(company_id, session_id)
        return {
            **_PER_TURN_RESET,
            "active_entities": sanitize_for_state(active_entities),
            "pending_clarification": pending_clarification,
        }

    return entry_node


def make_semantic_analysis_node(classifier, db):
    async def semantic_analysis_node(state: AgentState) -> dict:
        active_entities = entities_to_object_ids(state.get("active_entities", {}))
        result = await analyze(
            state["utterance"],
            classifier,
            to_object_id(state["company_id"]),
            db,
            session_state={"active_entities": active_entities, "pending_clarification": state.get("pending_clarification")},
            now=state["now"],
        )
        return {
            "raw_intent": result.raw_intent,
            "final_intent": result.final_intent,
            "entities": sanitize_for_state(result.entities),
            "unresolved_required": result.unresolved_required,
            "ambiguous": sanitize_for_state(result.ambiguous),
            "secondary_raw_intent": result.secondary_raw_intent,
            "secondary_entities": sanitize_for_state(result.secondary_entities),
            "secondary_unresolved_required": result.secondary_unresolved_required,
            "secondary_ambiguous": sanitize_for_state(result.secondary_ambiguous),
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
        # Filtered by entity type mentioned in THIS utterance before being offered to route()'s
        # memory-fill: real bug, found live. "where is my driver" (in a session with an
        # already-active vehicle) classified as GET_VEHICLE_LOCATION via the bare "where is"
        # phrase; Phase 6 correctly left vehicle_ref unresolved (no pronoun in "my driver"),
        # but route()'s memory-fill is unconditional — it filled in the stale vehicle anyway,
        # producing a confident, specific-sounding but wrong-context GPS answer instead of a
        # clarifying question. "where is my vehicle" (no entity-type word contradicting the
        # active vehicle) is unaffected — the filter only narrows, never expands. See
        # test_router_node_does_not_fill_vehicle_from_memory_when_utterance_asks_about_driver.
        filtered_active_entities = coreference.filter_active_entities_by_mentioned_type(
            state.get("utterance", ""), state.get("active_entities", {})
        )
        decision = route(
            state["raw_intent"],
            state.get("entities", {}),
            {"active_entities": filtered_active_entities},
            state.get("ambiguous", {}),
        )
        # Correct final_intent when route()'s own memory-fill resolves what Phase 6's
        # final_intent (still possibly "CLARIFICATION_NEEDED") didn't: if a tool is actually
        # about to run for raw_intent (route_condition sends every TOOL_CALL outcome straight to
        # a tool node, always), the intent that "actually happened" this turn IS raw_intent —
        # not Phase 6's earlier, now-superseded guess. Real bug, found live: "where is my
        # vehicle" (no pronoun, so Phase 6's own coreference fill never fired) reused an active
        # vehicle via route()'s unconditional memory-fill and genuinely answered the location
        # question, but ChatService/chat_messages.intent still reported "CLARIFICATION_NEEDED" —
        # correct response, mislabeled record. See
        # test_router_node_corrects_final_intent_when_memory_fill_resolves_it below.
        final_intent = state["raw_intent"] if decision.outcome == "TOOL_CALL" else state["final_intent"]

        # Dual-intent (Q2's "middle option"): only attempted when the primary itself resolved
        # to a real tool call — a secondary alongside a clarification-needed or backlog primary
        # isn't handled (out of scope for this pass). Routed the same way the primary is,
        # including the same entity-type memory-fill filter (filtered_active_entities) —
        # otherwise the secondary could reuse a stale entity of the wrong type exactly the way
        # the primary bug above did.
        secondary_decision = None
        secondary_raw_intent = state.get("secondary_raw_intent")
        if decision.outcome == "TOOL_CALL" and secondary_raw_intent:
            secondary_decision = route(
                secondary_raw_intent,
                state.get("secondary_entities", {}),
                {"active_entities": filtered_active_entities},
                state.get("secondary_ambiguous", {}),
            )
            # Defensive: detect_second_intent/pipeline.analyze() already filter out meta/
            # backlog candidates, so this shouldn't trigger in practice — kept as a second,
            # independent check rather than trusting a single filter point.
            if secondary_decision.outcome not in ("TOOL_CALL", "CLARIFICATION_NEEDED"):
                secondary_decision = None

        # Compound final_intent when a secondary actually contributes to this turn — reporting
        # only the primary here would be the same "final_intent doesn't reflect what actually
        # happened" bug in a new form (see the correction above), just for the two-intent case.
        if secondary_decision is not None:
            final_intent = f"{final_intent}+{secondary_raw_intent if secondary_decision.outcome == 'TOOL_CALL' else 'CLARIFICATION_NEEDED'}"

        return {
            "route_outcome": decision.outcome,
            "final_intent": final_intent,
            "tool_name": decision.tool_name,
            "subsystem": decision.subsystem,
            "route_params": decision.params,
            "clarifying_question": decision.clarifying_question,
            "missing_entity": decision.missing_entity,
            "secondary_route_outcome": secondary_decision.outcome if secondary_decision else None,
            "secondary_tool_name": secondary_decision.tool_name if secondary_decision else None,
            "secondary_subsystem": secondary_decision.subsystem if secondary_decision else None,
            "secondary_route_params": secondary_decision.params if secondary_decision else {},
            "secondary_clarifying_question": secondary_decision.clarifying_question if secondary_decision else None,
            "secondary_missing_entity": secondary_decision.missing_entity if secondary_decision else None,
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


def make_clarify_node(session_repo):
    async def clarify_node(state: AgentState) -> dict:
        # raw_intent is always a real actionable intent here, never a NONE-subsystem meta
        # intent: route() only ever returns CLARIFICATION_NEEDED for an intent with its own
        # `required`/`required_one_of`, and route_condition() only sends CLARIFICATION_NEEDED
        # outcomes here. Recorded so the very next turn can complete this intent directly if it
        # resolves just what's missing — see SessionRepository.set_pending_clarification.
        await session_repo.set_pending_clarification(
            to_object_id(state["company_id"]),
            to_object_id(state["session_id"]),
            intent=state["raw_intent"],
            missing=state["missing_entity"],
            now=state["now"],
        )
        return {"response_text": state.get("clarifying_question") or "Could you clarify what you're asking about?"}

    return clarify_node


async def _execute_secondary_tool(state: AgentState, *, db, gps_client, llm, kb_collection) -> dict | None:
    """Runs the secondary intent's tool, if router_node found one — called from whichever
    PRIMARY tool node actually executes (gps_tool/mongo_tool/rag_tool), since the secondary can
    be from a DIFFERENT subsystem than the primary (e.g. GET_DRIVER_ROSTER primary + LIVE_API
    GET_VEHICLE_LOCATION secondary) and therefore needs a dependency the primary node wasn't
    otherwise passed. This is why all three tool node factories now receive all four
    dependencies (db/gps_client/llm/kb_collection), not just the one their own primary
    subsystem needs."""
    if state.get("secondary_route_outcome") != "TOOL_CALL":
        return None
    decision = RouteDecision(
        outcome="TOOL_CALL",
        intent=state["secondary_raw_intent"],
        tool_name=state["secondary_tool_name"],
        subsystem=state["secondary_subsystem"],
        params=entities_to_object_ids(state.get("secondary_route_params", {})),
    )
    try:
        result = await execute_tool(
            decision,
            company_id=to_object_id(state["company_id"]),
            gps_client=gps_client,
            db=db,
            llm=llm,
            kb_collection=kb_collection,
            now=state["now"],
        )
    except LLMUnavailableError:
        # Same graceful-degradation shape rag_tool_node uses below for a primary RAG/
        # GENERAL_FALLBACK result — only reachable here when secondary_subsystem is one of
        # those two, since raw-data (LIVE_API/MONGO_REPO) handlers never call the LLM during
        # execution.
        result = {"answer": LLM_UNAVAILABLE_RESPONSE, "citations": [], "llm_invoked": False}
    if dataclasses.is_dataclass(result):
        result = dataclasses.asdict(result)
    return sanitize_for_state(result)


def make_gps_tool_node(gps_client, *, db=None, llm=None, kb_collection=None):
    async def gps_tool_node(state: AgentState) -> dict:
        # company_id is required by GET_FLEET_LIVE_STATUS (the one LIVE_API tool scoped to the
        # whole fleet rather than a single vehicle_id in params) — this node never passed it,
        # so that intent crashed with a TypeError the moment it actually ran. Every other
        # LIVE_API handler's **_ harmlessly absorbs the now-always-passed kwarg it doesn't need.
        # Found via live testing, not caught by any existing test (none exercised this intent
        # past classification — see the regression test added alongside this fix).
        result = await execute_tool(
            _decision_from_state(state), company_id=to_object_id(state["company_id"]), gps_client=gps_client, now=state["now"]
        )
        update = {"tool_result": sanitize_for_state(result)}
        secondary = await _execute_secondary_tool(state, db=db, gps_client=gps_client, llm=llm, kb_collection=kb_collection)
        if secondary is not None:
            update["secondary_tool_result"] = secondary
        return update

    return gps_tool_node


def make_mongo_tool_node(db, *, gps_client=None, llm=None, kb_collection=None):
    async def mongo_tool_node(state: AgentState) -> dict:
        result = await execute_tool(
            _decision_from_state(state), company_id=to_object_id(state["company_id"]), db=db, now=state["now"]
        )
        update = {"tool_result": sanitize_for_state(result)}
        secondary = await _execute_secondary_tool(state, db=db, gps_client=gps_client, llm=llm, kb_collection=kb_collection)
        if secondary is not None:
            update["secondary_tool_result"] = secondary
        return update

    return mongo_tool_node


def make_rag_tool_node(llm, kb_collection, *, db=None, gps_client=None):
    async def rag_tool_node(state: AgentState) -> dict:
        # Caught here, not left to propagate: an unhandled LLMUnavailableError would abort the
        # graph before memory_update_node runs, silently losing an already-resolved entity
        # (e.g. an explicit vehicle_ref this turn) just because *generation* failed — found by
        # actually running the server end-to-end with no LLM configured, not by inspection. See
        # templates.LLM_UNAVAILABLE_RESPONSE's docstring for the full story.
        try:
            result = await execute_tool(_decision_from_state(state), llm=llm, kb_collection=kb_collection)
        except LLMUnavailableError:
            result = {"answer": LLM_UNAVAILABLE_RESPONSE, "citations": [], "llm_invoked": False}
        # RAGResult (RAG subsystem) -> plain dict; GENERAL_KNOWLEDGE's handler already returns
        # a plain str. Both are already checkpoint-safe (no ObjectId/datetime involved), but
        # asdict() keeps the dataclass out of state for a uniform, plain-data shape.
        if dataclasses.is_dataclass(result):
            result = dataclasses.asdict(result)
        update = {"tool_result": result}
        secondary = await _execute_secondary_tool(state, db=db, gps_client=gps_client, llm=llm, kb_collection=kb_collection)
        if secondary is not None:
            update["secondary_tool_result"] = secondary
        return update

    return rag_tool_node


_DUAL_INTENT_NOTE = (
    "\n\n[This message asked about more than one thing. You are answering ONLY the part "
    "covered by the data above — a separate response covers the rest. Do not mention, "
    "reference, guess at, or apologize for the other part, even though you can see it in the "
    "question text above — treat it as if it were not part of the question at all.]"
)


async def _phrase_single_result(
    utterance: str, tool_result, subsystem: str | None, llm, is_dual_intent: bool = False
) -> tuple[str, list[dict]]:
    """One tool result -> (text, citations). Shared by the primary and, when present, the
    secondary result, so both are phrased identically — extracted from what was previously
    synthesis_node's only branch, unchanged in behavior for the single-intent case.

    is_dual_intent adds a much more explicit isolation note than Q1's base system prompt alone
    — found necessary by live testing: with the full compound utterance visible ("list drivers
    and MH12AB1234 location"), the primary phrasing call sometimes still commented on the
    OTHER topic ("the location of MH12AB1234 is not found in the data") immediately before the
    secondary's real answer contradicted it in the very next paragraph. The base system prompt
    alone wasn't reliably enough for an LLM to fully suppress commenting on a visibly-related
    topic in the question text; a much more explicit per-call note, appended to the utterance
    itself rather than only the system prompt, closed the gap in re-testing."""
    if subsystem in ("RAG", "GENERAL_FALLBACK"):
        if isinstance(tool_result, dict) and "answer" in tool_result:
            return tool_result["answer"], tool_result.get("citations", [])
        return str(tool_result), []

    effective_utterance = utterance + _DUAL_INTENT_NOTE if is_dual_intent else utterance
    # LIVE_API / MONGO_REPO: raw structured data, not yet natural language. Same
    # catch-inside-the-node reasoning as rag_tool_node — must not abort the graph before
    # memory_update_node runs.
    try:
        text = await phrase_tool_result(effective_utterance, tool_result, llm)
    except LLMUnavailableError:
        text = LLM_UNAVAILABLE_RESPONSE
    return text, []


def make_synthesis_node(llm):
    async def synthesis_node(state: AgentState) -> dict:
        outcome = state["route_outcome"]

        if outcome == "CLARIFICATION_NEEDED":
            return {}  # clarify_node already set response_text

        if outcome in ("NO_TOOL", "BACKLOG_UNSUPPORTED", "UNKNOWN_INTENT"):
            return {"response_text": direct_response(outcome, state.get("final_intent", ""))}

        has_secondary = state.get("secondary_tool_result") is not None or state.get("secondary_route_outcome") == "CLARIFICATION_NEEDED"
        primary_text, primary_citations = await _phrase_single_result(
            state.get("utterance", ""), state.get("tool_result"), state.get("subsystem"), llm, is_dual_intent=has_secondary
        )

        # Dual-intent (Q2's "middle option"). Two sub-cases, both appending rather than
        # blocking: if the secondary also resolved, phrase it the same way and join with a
        # blank line — a complete, confident answer to each part, per Q1's fix (each half is
        # phrased from only its own data, so neither mentions the other's topic). If the
        # secondary needs a missing entity instead, the primary is answered in full and the
        # secondary's clarifying question is appended as a follow-up — a combined single
        # question that blocks the whole turn would throw away a fully-answerable half; see
        # app/nlu/second_intent.py's docstring and the design note in this session's history
        # for why this was chosen over blocking. memory_update_node records this as a pending
        # clarification (same mechanism a single-intent CLARIFICATION_NEEDED turn uses) so a
        # bare follow-up reply next turn resumes the secondary intent instead of hitting
        # OUT_OF_SCOPE with no context.
        secondary_tool_result = state.get("secondary_tool_result")
        if secondary_tool_result is not None:
            secondary_text, secondary_citations = await _phrase_single_result(
                state.get("utterance", ""), secondary_tool_result, state.get("secondary_subsystem"), llm, is_dual_intent=True
            )
            return {
                "response_text": f"{primary_text}\n\n{secondary_text}",
                "citations": primary_citations + secondary_citations,
            }

        if state.get("secondary_route_outcome") == "CLARIFICATION_NEEDED":
            question = state.get("secondary_clarifying_question") or "Could you clarify the other part of your question?"
            return {"response_text": f"{primary_text}\n\n{question}", "citations": primary_citations}

        return {"response_text": primary_text, "citations": primary_citations}

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

        # Dual-intent secondary clarification: clarify_node only fires (and only records
        # pending_clarification) when route_outcome itself is CLARIFICATION_NEEDED — but here
        # the primary succeeded (route_outcome is TOOL_CALL) and only the SECONDARY needs
        # clarification, so clarify_node never runs this turn. Recorded here instead, via the
        # same mechanism, so a bare follow-up reply (e.g. just a plate number) resumes the
        # secondary intent next turn instead of hitting OUT_OF_SCOPE with no context — see
        # make_synthesis_node's docstring for why the primary is still answered in full rather
        # than blocking behind a combined question.
        if state.get("secondary_route_outcome") == "CLARIFICATION_NEEDED":
            await session_repo.set_pending_clarification(
                company_id, session_id, intent=state["secondary_raw_intent"], missing=state["secondary_missing_entity"], now=now
            )

        return {}

    return memory_update_node
