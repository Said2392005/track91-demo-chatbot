# FastAPI Backend — Phase 11

## Objective

Expose the graph (Phase 10) as a real, callable HTTP service — the first phase where the whole
system can actually be chatted with, not just tested in isolation. Routers/services/
repositories/DI, JWT auth with `company_id` scoping enforced at the repository layer (ADR 004),
structured JSON logging with `request_id`/`session_id` correlation, global exception handling,
pydantic-settings config.

## Structure

```
app/
├── main.py                 # app factory: lifespan builds every singleton once, correlation
│                              middleware, global exception handler, router includes
├── core/
│   ├── config.py            # extended: jwt_secret_key/algorithm/expiry, log_level
│   ├── security.py           # bcrypt password hashing, JWT issue/verify
│   └── logging.py             # JSON formatter, request_id/session_id contextvars
├── api/
│   ├── deps.py                 # DI: get_db/get_graph are the two roots everything else builds on
│   ├── object_id_param.py       # ObjectId parsing -> 400, not a raw crash
│   └── routers/{auth,chat,health}.py
├── services/{auth_service,chat_service}.py
├── schemas/{auth,chat}.py       # pydantic request/response models
└── db/repositories/{user_repository,chat_message_repository}.py   # new this phase
```

## Endpoints

`POST /auth/login`, `POST /chat`, `GET /chat/{session_id}/history`, `GET /health`, `GET /ready`.

`company_id` in every authenticated request comes from the verified JWT payload
(`CurrentUser.company_object_id`, `app/api/deps.py`) — never from a client-supplied field.
Cross-tenant access needs no separate check: `SessionRepository.get()` is already
`company_id`-scoped (ADR 004), so a session belonging to another company simply isn't found,
which `ChatService` turns into `SessionNotFoundError` → 404.

## DI design: two roots, not eleven

`get_db` and `get_graph` (`app/api/deps.py`) read from `request.app.state`, populated once by
`main.py`'s `lifespan`. Every other dependency (`get_user_repo`, `get_session_repo`,
`get_chat_service`, ...) builds on those two via `Depends()`. Overriding just the two roots in
`app.dependency_overrides` cascades through the whole tree — the mechanism the DI-override
tests use to swap in a fake agent graph without touching real Mongo/LLM/Chroma at all.

## LLM unavailability doesn't block startup — a deliberate design decision, tested twice

No `DEEPSEEK_API_KEY` is configured in this environment (confirmed at Phase 1 kickoff — mocked
everywhere). `DeepSeekProvider.__init__` raises `ValueError` on an empty key, and several
conversational paths (`GREETING`, `CHITCHAT`, `OUT_OF_SCOPE`, `BACKLOG_UNSUPPORTED`,
`CLARIFICATION_NEEDED`) don't need the LLM at all — so letting the whole app refuse to start
over a missing key would be needlessly harsh. `get_llm_provider()` (`app/llm/factory.py`) now
never raises: it falls back to `UnavailableLLMProvider`, whose `.generate()` raises
`LLMUnavailableError` only when something actually tries to use it. `app/router/registry.py`'s
handlers are unchanged; only the two Phase 10 nodes that call `.generate()`
(`rag_tool_node`/`synthesis_node`) needed to know what to do when it's unavailable.

## A real bug, found only by actually running the server — not by any test

Running the real server end-to-end (seeded data, ingested KB, no API key — exactly this
environment) surfaced what no test had caught: asking "Where is MH12AB1234?" then "What's its
speed?" in the same session returned a **clarifying question** on turn 2, instead of resolving
"its" via memory. Root cause: the original design let `LLMUnavailableError` propagate out of
`synthesis_node` and abort the graph *before* `memory_update_node` ran — so a vehicle reference
that had already resolved correctly in turn 1 was silently never persisted, purely because
*phrasing* the answer failed afterward. Fixed by catching `LLMUnavailableError` inside
`rag_tool_node` and `synthesis_node` themselves (`app/agent/nodes.py`), degrading to a shared
`LLM_UNAVAILABLE_RESPONSE` (`app/agent/templates.py`) without aborting the graph.
`ChatService`'s own catch is now a documented defensive backstop, not the primary handling.
Verified two ways: a new integration test
(`test_memory_persists_even_when_synthesis_llm_is_unavailable`) that switches to a working fake
LLM on turn 2 and confirms "its speed" still resolves via memory; and re-running the exact live
HTTP scenario against the real server afterward, confirming turn 2's `intent` came back
`GET_VEHICLE_SPEED`, not `CLARIFICATION_NEEDED`.

## Two more bugs, found by writing the router-contract tests



## Manual end-to-end verification (not just tests)

Seeded data, ingested the KB, started the real server (`uvicorn app.main:app`), and drove it
with `curl`: `/health`, `/ready`, `/auth/login` with the demo credentials
(`admin@cosmica-test.example` / `demo1234`, added to `seed_data.py` this phase — synthetic
dev-only credentials, per `non-goals.md`), then a real multi-turn `/chat` conversation and
`/chat/{id}/history`. This is what caught the memory-loss bug above — something no isolated
unit or DI-override test would have surfaced, since they don't chain a real generation failure
into a real subsequent turn against a real checkpointer.

## Testing

**17 new tests, 381/381 total passing** (364 carried forward — the 1 integration regression
test lives in `test_agent_graph_integration.py`, not counted separately here):

| File | Coverage |
|---|---|
| `test_api_health.py` | `/health` always 200; `/ready` 200 when Mongo reachable, 503 when not (via a `get_db` override pointed at an unreachable host) |
| `test_api_auth.py` | Login success/wrong-password/unknown-email/inactive-account, and a round-trip proving an issued token actually authorizes a protected route |
| `test_api_chat.py` | Auth enforcement, session creation vs. reuse, tenant isolation (404 for another company's session), malformed `session_id` → 400, transcript persistence, history retrieval — all against a **fake agent graph** via `app.dependency_overrides[deps.get_graph]`, decoupled from real LangGraph/LLM/Chroma |
| `test_agent_graph_integration.py` (+1) | The synthesis-failure memory-loss regression, through the real graph + real checkpointer |
