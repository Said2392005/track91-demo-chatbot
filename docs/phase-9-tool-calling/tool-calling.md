# API Tool Calling — Phase 9

## Objective

The deterministic intent-to-tool router (ADR 003) and the tool registry it dispatches to —
turning a classified intent + extracted entities (Phase 6) + active-entity memory (Phase 8)
into either a tool call with concrete params, or a defined non-tool outcome (clarification
needed, backlog-unsupported, no-tool-needed).

## `route()` is pure; `execute_tool()` is not — and that split is the point

`app/router/router.py`'s `route(intent, entities, memory_state)` is synchronous, has no I/O,
and never touches the LLM — matching ADR 003 exactly and the roadmap's Phase 9 test format,
`(intent, entities, memory-state) -> (tool called, params passed)`, verbatim as a function
signature. `execute_tool(decision, **deps)` is the separate async function that actually calls
a tool handler — this split is what makes the router exhaustively table-testable (15 pure cases
run in milliseconds, no Mongo/LLM needed) while keeping execution genuinely real (no mocks for
our own code) in a second, smaller set of tests.

## `memory_state` is a routing-layer safety net, not a replacement for Phase 6

Phase 6's entity extractor already resolves pronouns against active entities before the router
ever sees anything (`app/nlu/coreference.py`, `app/nlu/pipeline.py`). `route()` still checks
`memory_state["active_entities"]` itself, as a last-resort fill-in for any required entity
still missing from `entities` by the time it gets here — deliberate defense-in-depth, not
duplicated logic for its own sake. Verified not to override an explicit entity already present
in the current message (`test_memory_state_does_not_override_an_explicit_entity_in_this_message`).

## Tool registry (`app/router/registry.py`)

One entry per MVP intent (24 of the 31 in the taxonomy — the 4 backlog action intents and the
5 meta intents from `intent-taxonomy.md`'s section C/E deliberately have no registry entry;
`route()` handles those outcomes before ever consulting it):

| Subsystem | Handlers | Backing |
|---|---|---|
| `LIVE_API` | `app/tools/live_data_tools.py` (6) | `FleetGPSClient` interface + `MockFleetGPSClient` (new this phase — deterministic pseudo-random data seeded per vehicle_id, never persisted) |
| `MONGO_REPO` | `app/tools/history_tools.py` (10) | Extended repositories: new `TripRepository`, `AlertRepository`, `MaintenanceRepository`; `VehicleRepository`/`DriverRepository`/`GeofenceRepository` gained roster/listing methods |
| `RAG` | `app/tools/kb_tools.py` (6) | Phase 7's `answer_kb_query()`, one explicitly-named function per intent with its `category` hardcoded in the function body |
| `GENERAL_FALLBACK` | `app/tools/general_knowledge.py` (1) | Direct `LLMProvider.generate()` call — no retrieval, no gate |

### Why `PRICING`'s wiring is provable, not just documented

`kb_tools.pricing()` is its own named function whose body is
`answer_kb_query(query, "pricing", llm, ...)` — not a generic dispatcher keyed by a runtime
category lookup. That makes `TOOL_REGISTRY["PRICING"].handler is kb_tools.pricing` a direct,
literal proof that this intent always goes through the gated pipeline
(`test_pricing_tool_is_the_gated_rag_handler_not_a_bare_llm_call`), and a second execution-level
test reruns Phase 7's isolated-unapproved-collection scenario through the full
`route()` → `execute_tool()` path specifically, confirming the gate holds through this phase's
plumbing too, not just Phase 7's.

### `EXPLAIN_ALERT_TYPE`'s category mapping

Maps to `"feature_guide"` — no dedicated `documents_meta` source type exists for alert-type
explanations specifically (Phase 4 never authored one). This only affects citation labeling:
`category` in `answer_kb_query()` exists solely to trigger the `PRICING` gate, not to filter
which documents are searched — retrieval always searches the whole collection regardless
(`app/kb/retrieve.py`).

### A real, disclosed data gap: `GET_FUEL_CONSUMPTION_REPORT`

Trips (`app/db/schema_definitions.py`, Phase 3) record `distance_km`/`duration_minutes`/speed —
not fuel used. There's no real data in this schema to compute a fuel consumption report from.
Rather than approximate consumption from distance (which would misrepresent unmeasured data as
a real figure), the handler returns `{"available": False, "reason": "..."}` — an honest gap,
not a fabricated number.

### Clarifying questions are templates, not LLM calls

`app/router/clarification.py` — fixed strings keyed by the missing entity requirement. Keeping
this deterministic (like routing itself) means "which vehicle?" costs nothing and needs no LLM
round-trip; per ADR 003, only final-answer *phrasing* is the LLM's job, and a clarifying
question for a missing required field doesn't need any phrasing help.

## Testing

**22 new tests, 346/346 total passing** (324 carried forward):

| File | Coverage |
|---|---|
| `test_router.py` | 15-row table (`(intent, entities, memory_state) -> outcome`) covering every outcome type: `TOOL_CALL` (live-GPS, Mongo-history, RAG, `PRICING`, `GENERAL_KNOWLEDGE`), `CLARIFICATION_NEEDED` (missing required, unmet `required_one_of`), memory-state fill-in (and non-override), `BACKLOG_UNSUPPORTED`, `NO_TOOL` (meta intent), `UNKNOWN_INTENT` |
| `test_router_execution.py` | `execute_tool()` against real deps: mock GPS client, real Mongo (seeded trip), real ChromaDB + `FakeLLMProvider` (KB intent, `PRICING` approved case, `PRICING` no-approved-doc case reran through this phase's own path), `GENERAL_KNOWLEDGE`'s direct LLM call, and the "can't execute a non-`TOOL_CALL` decision" guard |
