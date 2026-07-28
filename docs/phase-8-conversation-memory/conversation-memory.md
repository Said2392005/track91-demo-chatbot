# Conversation Memory — Phase 8

## Objective

Give Phase 6's coreference resolution ("its speed") somewhere real to read active-entity state
from, and give Phase 10's future LangGraph graph a working checkpointer to compile against —
both with expiry, not indefinite persistence.

## Two separate memory concerns, deliberately not merged

Per the Phase 2 component diagram, "Session Memory" is two boxes, not one — and they stay
separate here:

1. **LangGraph checkpointer** (`app/memory/checkpointer.py`) — raw graph/message state, keyed
   by `thread_id` (our `session_id`), serialized via LangGraph's own protocol. Uses the
   official `langgraph-checkpoint-mongodb` package rather than a hand-rolled saver — correctly
   implementing LangGraph's checkpoint serialization is non-trivial, and this is the
   maintained, official integration.
2. **Active-entity tracker** (`app/memory/active_entity_tracker.py` +
   `app/db/repositories/session_repository.py`) — domain data (which vehicle/driver/geofence is
   "active" for coreference), a plain dict Phase 6's `pipeline.analyze()` already knows how to
   consume (`session_state={"active_entities": {...}}`). Goes through our own repository layer
   (ADR 001), not LangGraph's serialization.

They share one deliberate wiring point: both expire on the same clock family
(`settings.session_ttl_seconds` for the checkpoint TTL and the session document's own TTL;
`settings.active_entity_ttl_seconds`, shorter, for the active-entity reference specifically).

## One narrow, documented exception to "motor everywhere"

`MongoDBSaver` (the official LangGraph integration, v0.4.0) takes a sync `pymongo.MongoClient`
in its constructor — there's no motor-native variant in this version. Every call site in this
codebase uses its *async* methods (`aget_tuple`/`aput`/`alist`/...), which the library itself
dispatches through a thread executor, so the event loop is never blocked despite the sync
client underneath. This is flagged explicitly in `checkpointer.py`'s docstring as the one
deliberate exception to ADR 001's "only repository modules import motor" — scoped to that one
file, not a general relaxation of the rule.

## Expiry — the Phase 8 requirement, implemented at two layers

1. **Session-level TTL** (`settings.session_ttl_seconds`, default 24h): a genuine MongoDB TTL
   index on `chat_sessions.last_active_at` (`app/db/indexes.py`) and the checkpointer's own
   `ttl` parameter on its `created_at` field. Because `SessionRepository.touch()` bumps
   `last_active_at` on every turn, and MongoDB's TTL monitor re-evaluates against a document's
   *current* field value on every sweep (not its value at insert time), this is a genuine
   sliding idle-timeout — a session expires N seconds after its *last* activity, not N seconds
   after it started.
2. **Active-entity-level TTL** (`settings.active_entity_ttl_seconds`, default 30 min),
   enforced in application code (`active_entity_tracker.get_active_entities()`), not a Mongo TTL
   index — a much shorter window than the session itself, and checked precisely at read time
   rather than relying on MongoDB's TTL monitor (which runs on a ~60s background sweep, too
   imprecise for this). A vehicle discussed 3 hours ago in an otherwise-still-open session
   should not silently answer "its speed" — the session can stay alive far longer than any
   single entity reference should stay "active."

Both are flagged assumptions (reasonable pilot defaults, not measured against real usage) —
same spirit as the India-plate-format and IST-timezone assumptions flagged in earlier phases.

## A datetime bug this phase surfaced, fixed at the client level

Implementing the TTL check (`now - active_entities_updated_at`) was the first place in this
codebase to actually subtract a datetime read back from Mongo from a fresh `datetime.now()`.
Verified empirically before writing the fix: Motor's default client returns **naive**
datetimes on read, even though every write in this codebase uses timezone-aware UTC values —
the subtraction raises `TypeError: can't subtract offset-naive and offset-aware datetimes`.
Fixed at `app/db/client.py`'s single client factory (`tz_aware=True`), not patched around
locally in the tracker — any future phase doing datetime arithmetic against a Mongo-read value
would have hit the exact same bug. `tests/conftest.py`'s test fixture updated to match, so tests
exercise the same behavior as the real app.

## Active-entity replacement policy

Resolves the open question flagged in `entity-taxonomy.md`'s Phase 8 notes ("does asking about
a different vehicle replace the active vehicle, or stack?"): **replace**. Setting a new active
vehicle overwrites the previous one for that entity type — there's no history/stack. This
matches ordinary conversational expectation ("it" means whatever was discussed most recently)
and keeps the active-entity read path a single field lookup, not a most-recent-of-a-list scan.

## Testing

**16 new tests, 324/324 total passing** (308 carried forward):

| File | Coverage |
|---|---|
| `test_session_repository.py` | CRUD, tenant scoping, `touch()`, active-entity set/replace |
| `test_active_entity_tracker.py` | TTL boundary cases: fresh, just-inside, just-past, unset, invalid entity type |
| `test_checkpointer.py` | Real `aput`/`aget_tuple` round-trip, thread isolation, TTL index existence/value |
| `test_conversation_memory_integration.py` | The requested scripted scenario, both directions |

### The requested scripted scenario, both directions

`test_its_speed_resolves_to_the_previously_mentioned_vehicle` — turn 1 ("Where is
MH12AB1234?") resolves and persists the active vehicle; turn 2 ("What's its speed?"), run as a
genuinely separate call sharing only `session_id`, resolves "its" to that same vehicle and
reaches `GET_VEHICLE_SPEED` cleanly rather than `CLARIFICATION_NEEDED`.

`test_its_speed_does_not_resolve_once_active_entity_has_expired` — identical script, but turn 2
happens `active_entity_ttl_seconds + 60` later: the active-entity fetch returns `{}`, and
`pipeline.analyze()` correctly falls to `CLARIFICATION_NEEDED` instead of resolving "its" to a
stale reference. Proves expiry changes real behavior end-to-end, not just that a TTL number is
configured somewhere.
