# Testing — Phase 12

## Objective

Full test pyramid, the AI eval golden-set harness (40-60 Q&A pairs, intent/entity/retrieval/
faithfulness scoring), load testing, and re-verification of the "its speed" scenario. Built
against `FakeLLMProvider` per project decision (a real DeepSeek key isn't configured yet) —
everything is designed to swap to a real provider with a one-line change; see the walkthrough
at the end of this doc.

## The pyramid, end to end

| Layer | Where | What's real |
|---|---|---|
| Unit | Phases 3-11's per-module tests (`test_router.py`, `test_context_assembler.py`, `test_agent_nodes.py`, `app/eval/scorer.py`'s pure functions, ...) | Varies — pure functions have no dependencies at all |
| Integration | `test_agent_graph_integration.py`, `test_router_execution.py`, `test_kb_ingestion.py`, ... | Real Mongo, real ChromaDB, real cross-encoder — fake LLM |
| Contract (API, DI-override) | Phase 11's `test_api_*.py` | Real Mongo via `get_db` override; **fake agent** via `get_graph` override |
| **E2E (new this phase)** | `test_e2e_full_stack.py` | The actual FastAPI app object, actual `lifespan`, real Mongo-backed checkpointer, real ChromaDB — only the LLM is faked |
| **Load (new this phase)** | `loadtest/locustfile.py`, run against a real local server | Everything real except the LLM (degrades gracefully, per Phase 11) |
| **AI eval (new this phase)** | `app/eval/` + `test_eval_harness.py` | Real classifier, real Mongo entity resolution, real ChromaDB retrieval — fake LLM for generation |

The E2E layer is a genuine step up from Phase 11's contract tests: those override `get_graph`
with a fake agent to test the router/service contract in isolation; this drives the real
compiled graph through real HTTP requests against the real app, with `TestClient` used as a
context manager specifically because it — unlike the raw `httpx.ASGITransport` Phase 11 used —
actually triggers `lifespan` (verified directly before writing this file, not assumed).

## AI eval golden-set harness (`app/eval/`)

`golden_set.py` — 44 cases, covering all 33 taxonomy intents (32 via the classifier's raw
output, `CLARIFICATION_NEEDED` via the pipeline's downstream decision, since it's never a raw
classifier output by design). `scorer.py` — pure scoring functions. `runner.py` — orchestration
+ a standalone CLI (`python -m app.eval.runner [--real-llm]`).

Four metrics:
- **Intent-classification accuracy** — both `raw_intent` (classifier output) and `final_intent`
  (post entity-resolution, since a few cases are designed to diverge — see `CLARIFICATION_NEEDED`
  above).
- **Entity-extraction accuracy** — symbolic expected values (`"plate:MH12AB1234"`,
  `"driver:Ramesh Kumar"`) resolved against seeded fixtures at eval time, not hardcoded ObjectIds.
- **Retrieval precision** — at least one relevant doc in the top-k retrieved chunks, for the 12
  RAG cases with real KB ground truth.
- **Answer faithfulness, as a citation-groundedness proxy** — with a fake LLM, there's no
  generated prose to check for hallucination against. What *is* measurable, and what's actually
  under this system's control, is whether the **context the LLM would see** is grounded: does
  every citation trace to a doc this case considers relevant (and, for `PRICING` cases, is every
  citation actually approved)? This is a proxy, not the real thing — noted explicitly rather
  than implied to be more than it is.

### A disclosed gap, not fabricated ground truth

`EXPLAIN_ALERT_TYPE` and `GENERAL_KNOWLEDGE` cases score intent classification only, with no
`kb_category`/`relevant_doc_ids`. This synthetic KB has no dedicated alert-type glossary
document (Phase 4 never authored one) and `GENERAL_KNOWLEDGE` is never KB-backed by design —
there's no ground truth to score retrieval against for either, so none was invented.

## Real bugs found by actually running the harness — none were fixed by adjusting the test

The first real run (44 cases): 90.9% raw intent accuracy, 86.4% final intent accuracy, 72.7%
citation groundedness. Each failure was individually diagnosed before deciding whether to fix
the code or fix a wrong expectation in the golden set itself:

1. **`ASSIGN_DRIVER_TO_VEHICLE`'s trigger regex bug.** `\bassign \w+ to\b` — `\w+` matches a
   single word only, so "Assign **Ramesh Kumar** to MH12AB1234" (a two-word name) never
   matched. Fixed the regex to allow 1-3 words.
2. **`EXPLAIN_FEATURE` missing a realistic verb.** "What **happens when** a vehicle enters or
   exits a geofence?" — none of the existing cooccurrence verbs ("how does", "what is", ...)
   covered "what happens". Added it.
3. **`TROUBLESHOOTING_DEVICE` missing a tense variant.** "Why would a GPS device **stop**
   sending data?" only matched the past-tense "device **stopped** sending" phrase. Added the
   base-tense variant.
4. **`PRICING` missing a real phrasing.** "What's **included in** the Enterprise plan?" has
   none of "cost"/"price"/"pricing" at all. Added "included in the" as a trigger.
5. **A real content-safety gap, the most significant finding this phase**: a `POLICY_QUESTION`
   about data retention returned a citation from **"Draft Enterprise Pricing Notes"** — the
   internal, explicitly-never-to-be-quoted-to-a-customer draft doc. The `PRICING` gate
   (`assemble_pricing_context`) only ever protected `PRICING`-routed queries; nothing stopped
   unapproved pricing content from surfacing as an incidental retrieval hit on an unrelated
   question. Fixed `assemble_context()` (the general, non-gated path) to also exclude
   `category: pricing` chunks that aren't approved — a narrower filter than the `PRICING` gate's
   (which would wrongly exclude nearly everything if applied generally, since `approved_pricing`
   defaults to `False` for every non-pricing chunk by convention). Verified with two new
   regression tests in `test_context_assembler.py`.
6. **Two of my own golden-set expectations were wrong, not the system**: `CREATE_GEOFENCE` and
   `SCHEDULE_MAINTENANCE`'s `final_intent` legitimately downgrades to `CLARIFICATION_NEEDED` —
   `location_ref` extraction is genuinely unimplemented (documented since Phase 6, since
   `CREATE_GEOFENCE` stays backlog), and `date_parser.py` genuinely doesn't recognize "next
   week". Fixed the golden set's expectations, not the code — the code's behavior was correct.
7. **`ASSIGN_DRIVER_TO_VEHICLE`'s entity resolution, a disclosed (not fixed) gap**: even after
   fix #1 got the intent classified correctly, `driver_ref` extraction's proper-noun regex
   greedily pairs the sentence-initial capitalized verb "Assign" with the next capitalized word
   ("Ramesh"), producing candidates `["Assign Ramesh", "Kumar"]` — neither resolves. Documented
   in the golden set rather than fixed, since `ASSIGN_DRIVER_TO_VEHICLE` stays backlog/
   unimplemented regardless of entity-resolution quality.

Final run: **100% raw intent accuracy, 100% final intent accuracy, 100% entity accuracy, 100%
retrieval precision, 81.8% citation groundedness.** The remaining groundedness gap (2 of 11
scored RAG cases) is the same small-KB retrieval imprecision Phase 7 already measured and
documented (~87-94% precision@k on this 28-chunk KB) — not chased further here for the same
reason it wasn't chased in Phase 7. Test thresholds (`test_eval_harness.py`) are set with real
margin below these measured numbers.

## Load testing (`loadtest/locustfile.py`)

Run against a real local server (seeded data, ingested KB, no LLM key — the actual state of
this environment): `locust -f loadtest/locustfile.py --headless -u 10 -r 2 -t 45s --host
http://127.0.0.1:8000`.

### A real, serious bug found by the very first run

`/auth/login`'s latency was absurd for a login endpoint: **median 5.2s, max 7.8s**, under just
10 concurrent users. Root cause, confirmed by reading the code rather than guessing:
`AuthService.login()` called `bcrypt.checkpw()` — a synchronous, CPU-bound, deliberately-slow
call — directly inside an `async def` method. That blocks Python's single asyncio event loop for
the full hash computation, serializing every concurrent login behind it instead of running them
in parallel; a textbook blocking-call-in-an-async-handler bug. Fixed with `asyncio.to_thread()`
to offload the bcrypt call to a worker thread.

**Re-ran the identical load test after the fix**: median `/auth/login` latency dropped to
**270ms — a ~19x improvement** (min 258ms, so the fix eliminated the queueing almost entirely;
the 258ms itself is just bcrypt's real, deliberate cost).

### An open finding, honestly characterized rather than over-claimed

Both runs (before and after the auth fix) show a long tail — P95+ response times spiking to
5-6+ seconds across **every** endpoint, including `/health`, which has zero application
dependencies. Since this tail was present in the *first* run too (confirmed by checking that
run's raw CSV output, not assumed), it predates and is unrelated to the auth fix — it's a
separate, still-open phenomenon. Given this sandboxed session runs Mongo, ChromaDB, the
embedding model, uvicorn, and Locust all concurrently on one shared local machine, the most
likely explanation is local resource contention, not an application bug — but this wasn't fully
isolated, and is reported as an open question for testing in a dedicated environment, not
claimed as diagnosed.

## Re-verifying "its speed" — now covered at every layer, with a real model still pending

The scenario is now verified through: Phase 10's graph integration test (real graph, real
checkpointer, no HTTP), Phase 11's contract test (fake graph, real HTTP), and this phase's
`test_its_speed_coreference_through_real_http_and_real_graph` (real graph, real HTTP, real
checkpointer — the only fake is the LLM). All pass. **Re-running it against a real DeepSeek
response specifically is still pending** — it needs `DEEPSEEK_API_KEY` configured, which hadn't
happened as of this phase. Once set:

```bash
cd backend
# restart the server, confirm the startup warning is gone, then:
curl -X POST http://127.0.0.1:8000/chat -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"message":"Where is MH12AB1234?"}'
# then, with the returned session_id:
curl -X POST http://127.0.0.1:8000/chat -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"message":"What'"'"'s its speed?","session_id":"<id>"}'
```

The second response's `intent` should be `GET_VEHICLE_SPEED` with real generated text (not the
`LLM_UNAVAILABLE_RESPONSE`) — the exact check already run manually in Phase 11, just with real
generation this time instead of the graceful-degradation path.

## Switching the eval harness / load test to a real LLM

`python -m app.eval.runner --real-llm` uses `get_llm_provider()` (the real DeepSeek adapter)
instead of `FakeLLMProvider`, once `DEEPSEEK_API_KEY` is set. The citation-groundedness proxy
stays meaningful either way (it never depended on the LLM's actual output); true answer-
faithfulness scoring (comparing generated prose against source content, not just checking
citations) would need a real model's output and isn't attempted with the fake — that's the one
metric this harness can't fully deliver until a key exists.

## Testing

**11 new tests, 394/394 total passing** (383 carried forward): 7 in `test_eval_harness.py`, 4
in `test_e2e_full_stack.py`. Plus 2 regression tests in `test_context_assembler.py` for the
pricing-leakage fix (counted in the 383 carried-forward base, added mid-phase alongside that
fix).
