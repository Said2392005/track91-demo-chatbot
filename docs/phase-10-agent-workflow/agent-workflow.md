# Agent Workflow — Phase 10

## Objective

Assemble Phases 6-9 into an actual LangGraph graph: `entry → semantic_analysis → router`,
conditional edges to `clarify` / `gps_tool` / `mongo_tool` / `rag_tool`, converging on
`synthesis → memory_update → end`. Per the brief, this phase is assembly — the only new code is
the graph wiring itself, the ObjectId↔string boundary conversion state serialization requires,
and response phrasing/templating for the two subsystems whose tools return raw data instead of
already-final text.

## Where side effects live

`router_node` and `clarify_node` are fully pure (`route()` has no I/O at all, by ADR 003).
`entry_node`/`semantic_analysis_node` do read-only Mongo lookups (entity resolution, active-
entity fetch) — inherent Phase 6/8 behavior, not new tool-calling. `synthesis_node` makes at
most one LLM call, only to phrase raw `LIVE_API`/`MONGO_REPO` data into natural language — RAG
and `GENERAL_KNOWLEDGE` results are already final text by the time they reach it (Phase 7/9
generate during tool execution), so the LLM is never called twice for the same answer. DB
writes and the Fleet GPS API are exclusively `gps_tool`/`mongo_tool`/`rag_tool`/
`memory_update`'s job. This is a documented interpretation of the phase's constraint, not
something the constraint states in code-checkable terms — worth being explicit that "the LLM
phrasing raw data" was deliberately not treated as a disallowed side effect, since that's the
LLM's designated job throughout this roadmap.

## Two real bugs, both found by the integration tests actually running — not by inspection

Both are the kind of bug that only exists once a graph runs multi-turn with a **real**
checkpointer — which is exactly why `tests/test_agent_graph_integration.py` uses a genuine
`MongoDBSaver` against test Mongo, not `compile()` with no checkpointer.

1. **`ObjectId` is not checkpoint-serializable.** Verified before writing any node code:
   `JsonPlusSerializer.dumps_typed({"oid": ObjectId()})` raises
   `TypeError: Type is not msgpack serializable: ObjectId`, while `datetime` round-trips fine.
   Every ID entering `AgentState` (`app/agent/state.py`) is therefore a plain string —
   `app/agent/serialization.py` converts at the node boundary, right before a repo/tool call
   needs a real `ObjectId` and right after one comes back. `test_mongo_tool_node_sanitizes_raw_mongo_documents`
   asserts zero raw `ObjectId` instances anywhere in a node's returned state.
2. **Router must route on `raw_intent`, not `final_intent`.** Phase 6's `pipeline.analyze()`
   already downgrades `final_intent` to `"CLARIFICATION_NEEDED"` when required entities are
   unresolved. Feeding that into Phase 9's `route()` — designed to receive an actionable intent
   like `"GET_VEHICLE_SPEED"` and make its own (superset — it also checks `memory_state`)
   determination — made `"CLARIFICATION_NEEDED"` look up as a `NONE`-subsystem meta intent in
   `app/core/taxonomy.py` and incorrectly resolve to `NO_TOOL`. Only surfaced in the
   active-entity-expiry integration test, where turn 2 genuinely needs fresh clarification;
   every earlier Phase 6/9 test happened to use cases where `raw_intent == final_intent`. Fixed
   in `router_node`; Phase 6's `final_intent`/`unresolved_required`/`ambiguous` remain in state
   as diagnostic output, but routing now keys off `raw_intent` — Phase 9's router is the
   authoritative "does this need clarification" decision for actionable intents.
3. **State doesn't reset between checkpointed turns.** With a checkpointer attached, LangGraph
   does *not* clear state between separate `ainvoke()` calls on the same `thread_id` — any key
   a node doesn't explicitly overwrite keeps its value from the previous turn's checkpoint.
   Turn 2 of the expiry scenario correctly routes to `clarify` (skipping every tool node
   entirely) — but without an explicit reset, `tool_result` still held turn 1's GPS location
   data. Fixed by having `entry_node` explicitly reset every per-turn field (`_PER_TURN_RESET`
   in `app/agent/nodes.py`) except `active_entities`, which is the one field meant to persist
   across turns by design (Phase 8).

## Testing

**18 new tests, 364/364 total passing** (346 carried forward):

| File | Coverage |
|---|---|
| `test_agent_nodes.py` | Every node in isolation — real Mongo/mock GPS/fake LLM, checked for zero raw `ObjectId` leakage, correct dispatch, and the `raw_intent`-vs-`final_intent` regression case |
| `test_agent_graph_integration.py` | 3 full multi-turn scenarios through the compiled graph with a real `MongoDBSaver`, each turn a separate `ainvoke()` call sharing only a `thread_id` |

### The three integration scenarios

1. **`test_its_speed_coreference_resolves_across_turns`** — the requested scripted scenario.
   Turn 1 resolves and persists `MH12AB1234`; turn 2, a genuinely separate call, resolves "its
   speed" to that vehicle and reaches `GET_VEHICLE_SPEED` cleanly.
2. **`test_its_speed_does_not_resolve_after_active_entity_expiry`** — same script, turn 2 lands
   `active_entity_ttl_seconds + 60` later: correctly falls to `CLARIFICATION_NEEDED`, and
   (post-fix) carries no stale `tool_result` from turn 1.
3. **`test_greeting_then_pricing_question_across_turns`** — session continuity for a
   non-coreference case, and the `PRICING` gate proven reachable through the entire graph:
   citations trace only to the approved pricing sheet.

## Pending-clarification resume (added post-Phase-12, real bug found in live testing)

`entry_node`/`clarify_node`/`app/nlu/pipeline.py`'s `analyze()` now track "we asked a clarifying
question for intent X, still missing Y" across turns (`SessionRepository.set_pending_clarification`
/ `pop_pending_clarification`, single-turn scoped — popped, not just read, on the very next
turn). Two real gaps this closes, found by actually using the bot in a browser, not by
inspection:

1. **Bare-entity replies were falling through to `OUT_OF_SCOPE`.** "where is my vehicle?" ->
   "which vehicle?" -> a bare "MH12AB1234" (no verb) has nothing for the classifier's trigger
   phrases to match, so it scored 0 everywhere and fell through to the `OUT_OF_SCOPE` fallback
   instead of completing `GET_VEHICLE_LOCATION`. Fixed: when the freshly-classified intent is a
   no-clear-trigger fallback (`OUT_OF_SCOPE`/`GENERAL_KNOWLEDGE`) and a pending clarification
   exists, entity extraction is retried against the *pending* intent before accepting the
   fallback — a message that clearly matches its own trigger phrase is never overridden this
   way. See `tests/test_agent_graph_integration.py::test_bare_vehicle_number_completes_pending_clarification`.
2. **`awaiting_clarification` was never actually set by a real conversation** — it only ever
   existed as a manually-passed flag in tests and the eval golden set, so a real "Yes"/"No"
   reply to a real clarifying question always misclassified as `OUT_OF_SCOPE` rather than
   `AFFIRM_DENY`. Now driven by the same pending-clarification state. See
   `test_affirm_deny_reply_to_a_real_clarifying_question` in the same file.

**Still an open, out-of-scope gap, not addressed by the above**: `AFFIRM_DENY` correctly
*classifies* now, but still has no multi-turn disambiguation-*resolution* flow behind it — there
remains no mechanism for a prior `CLARIFICATION_NEEDED` turn's ambiguous candidates (e.g. a
driver-name collision) to be remembered and picked between by a following "yes"/"no";
`AFFIRM_DENY` still only returns `app/agent/templates.py`'s generic "could you tell me again"
response. Not called for in Phase 1's taxonomy or any phase's stated test requirements, and
previously confirmed with the user as an acceptable gap — still true, just narrower than before.
