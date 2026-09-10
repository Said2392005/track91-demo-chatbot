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

## Real-model verification — history: DeepSeek (planned) → Groq (interim) → Bedrock (current)

A paid DeepSeek key was never available, so `GroqProvider` (OpenAI-compatible, free tier) was
added as an interim second `LLMProvider` adapter, config-driven swap (`LLM_PROVIDER=groq`) per
ADR 002. `DeepSeekProvider` and `GroqProvider` were refactored to share
`OpenAICompatibleProvider` once a second real concrete adapter needed the identical
request/response handling — extracted because the reuse was immediate and real, not
speculative.

With `GROQ_API_KEY` configured and `LLM_PROVIDER=groq`, the real server was started and driven
with real HTTP requests:

- **The "its speed" scenario**: turn 1 ("Where is MH12AB1234?") returned a real
  Groq-generated location answer; turn 2 ("What's its speed?"), same session, correctly
  resolved "its" via memory and returned `intent: GET_VEHICLE_SPEED` with a real generated
  speed answer — not the `LLM_UNAVAILABLE_RESPONSE` degraded path.
- **`PRICING`**: "How much does the Pro plan cost per month?" returned a real answer correctly
  citing both the monthly (₹1,049) and annual (₹899) figures from the approved pricing sheet,
  with citations tracing only to `Track91 Pricing Sheet`.
- **`EXPLAIN_FEATURE`**: "How does geofencing work?" returned an accurate, well-grounded
  multi-sentence answer citing the geofencing guide's actual content.
- **`python -m app.eval.runner --real-llm`**: identical results to the fake-LLM run (100%
  intent, 100% entity, 100% retrieval, 81.8% citation groundedness) — confirms, with real
  evidence rather than just the design claim, that these four metrics never depended on the
  LLM's actual output.

DeepSeek and Groq were both later removed in favor of `BedrockProvider` (AWS Bedrock,
gpt-oss-120b) — see the section below. This section is kept as the historical record of how the
strategy pattern (ADR 002) played out across three providers, not as a description of what's
currently configured.

## Bedrock migration (gpt-oss-120b) — golden set and max_tokens re-verification

`GroqProvider` and `OpenAICompatibleProvider` were deleted; `BedrockProvider`
(`app/llm/providers/bedrock.py`) is now the only configured provider (`LLM_PROVIDER=bedrock`).
It uses boto3, not HTTP, so it doesn't extend `OpenAICompatibleProvider` — but gpt-oss's
response body has the same `choices`/`usage` shape as the OpenAI chat-completions API, so usage
parsing was pulled into a small shared module (`app/llm/providers/usage.py`) rather than
importing a private function across adapters. gpt-oss also emits a hidden
`<reasoning>...</reasoning>` block before the visible answer, stripped inside the adapter so it
never reaches synthesis or the user (with a defensive fallback for an unclosed tag — see
`bedrock.py`'s module docstring; not observed in practice, since Bedrock appears to always close
the tag even under truncation, but that's not a documented contract).

**Golden set, real LLM, both providers** (`python -m app.eval.runner --real-llm`, run against
each provider in turn): identical results —

| Metric | Groq/Llama-3.3 | Bedrock/gpt-oss-120b |
|---|---|---|
| Raw intent accuracy | 100.0% | 100.0% |
| Final intent accuracy | 100.0% | 100.0% |
| Entity accuracy | 100.0% | 100.0% |
| Retrieval precision | 100.0% | 100.0% |
| Citation groundedness | 100.0% | 100.0% |

This isn't a coincidence and isn't evidence the two models produce identical prose — it's a
consequence of what the harness actually measures, already noted above: `intent_classifier_strategy`
defaults to `rule_based` (LLM-independent), and `score_citation_groundedness` checks which
*retrieved* chunks were used to build the context (`context.citations`, from
`app/rag/context_assembler.py`), not anything parsed out of the LLM's generated text. Swapping
the LLM provider cannot move any of these four numbers by construction; what the run does
confirm is that all 15 real RAG generation calls against Bedrock complete without error, same
as Groq. True per-provider answer-quality comparison would need human/model-graded review of
the actual generated prose, which this harness still doesn't attempt (real LLM or not — same
caveat as before).

**`llm_max_tokens` re-measurement**: 250 was tuned for Groq/Llama-3.3, which doesn't emit a
reasoning block. gpt-oss spends completion tokens on `<reasoning>` *before* the visible answer,
shrinking the effective budget for the same cap — confirmed by re-running
`TROUBLESHOOTING_DEVICE` (the same longest-answer case from the original Groq measurement)
directly against Bedrock:

| max_tokens | Repeated real calls | Truncated (`finish_reason="length"`) | Worst completion_tokens |
|---|---|---|---|
| 250 | 3 | 3/3 | 250 (cap) |
| 350 | 6 | 1/6 | 350 (cap) |
| 400 | 6 | 1/6 | 400 (cap) |
| 450 | 6 | 0/6 | 428 |
| 500 | 12 (two batches) | 0/12 | 388 |

`llm_max_tokens` is now **500** (`app/core/config.py`, `.env.example`) — cleared with headroom
above the worst observed completion-token count. See `tests/test_max_tokens_real_bedrock.py`
for the regression tripwire (the Bedrock counterpart of the now-deleted
`test_max_tokens_real_groq.py`), which also confirms `<reasoning>` never leaks into a visible
answer, truncated or not.

## Switching the eval harness / load test to a real LLM

`python -m app.eval.runner --real-llm` uses `get_llm_provider()` — currently always Bedrock,
but the call site doesn't know or care which provider `LLM_PROVIDER` selects. The
citation-groundedness proxy stays meaningful regardless of provider (it never depended on the
LLM's actual output, now confirmed above for both Groq and Bedrock); true answer-faithfulness
scoring (comparing generated prose against source content, not just checking citations) would
need systematic human or model-graded review of real output and isn't attempted here — that's
the one metric this harness still can't fully automate, real LLM or not.

## Testing

**11 new tests, 394/394 total passing** (383 carried forward): 7 in `test_eval_harness.py`, 4
in `test_e2e_full_stack.py`. Plus 2 regression tests in `test_context_assembler.py` for the
pricing-leakage fix (counted in the 383 carried-forward base, added mid-phase alongside that
fix).
