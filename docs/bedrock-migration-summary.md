# Groq → AWS Bedrock Migration Summary

## Overview

The project's LLM provider was switched from **Groq (Llama-3.3-70b, free tier)** to **AWS
Bedrock (gpt-oss-120b)**. This was possible as a config change plus one new adapter file
because of a design decision made early in the project (ADR 002): the rest of the codebase
never talks to a specific LLM vendor's SDK directly — everything goes through one generic
interface (`LLMProvider.generate()`), and only a small adapter module per provider knows how to
actually call that vendor's API. Swapping providers means writing one new adapter and changing
one config value; nothing else in the application changes.

The migration happened in four stages, in this order:
1. Add the Bedrock adapter and get a real call working, alongside Groq (both providers present).
2. Test it thoroughly and compare it against the Groq baseline on real, measured data.
3. Fix a token-budget setting that needed to change for the new model.
4. Only once the above confirmed Bedrock was solid, delete Groq entirely.

That order matters for this doc: Groq wasn't removed speculatively — it stayed in the codebase
until real evidence (test results, a side-by-side eval, live token measurements) showed Bedrock
was ready to replace it.

---

## New files created

| File | What it is |
|---|---|
| `backend/app/llm/providers/bedrock.py` | The Bedrock adapter itself — the only file in the codebase that imports `boto3` or knows AWS Bedrock exists. Builds the request, calls the model, strips gpt-oss's internal "thinking" text out of the answer, and returns the same generic response shape every other provider returns. |
| `backend/app/llm/providers/usage.py` | A small shared helper that reads token counts (prompt/completion) out of a response. Bedrock's gpt-oss model happens to return its response in the same JSON shape OpenAI-style APIs use, so this one parsing function is reused rather than duplicated. |
| `backend/tests/test_bedrock_provider.py` | Unit tests for the Bedrock adapter — request building, defaults, the "thinking" text getting stripped out (both the normal case and a defensive edge case), token-count parsing, and that a real AWS error propagates correctly. None of these make a real network call — they use a fake stand-in for the AWS client, so they run instantly and don't need AWS credentials. |
| `backend/tests/test_max_tokens_real_bedrock.py` | A separate, *opt-in* test file that does make real calls to AWS Bedrock, to verify answers aren't getting cut off. Only runs when real AWS credentials are present; skips itself cleanly otherwise so the rest of the test suite isn't affected. |

---

## Existing files modified

| File | What changed and why |
|---|---|
| `backend/app/core/config.py` | `llm_provider` default changed from `"groq"` to `"bedrock"`. Removed the `groq_api_key` setting (nothing reads it anymore). Added `bedrock_model_id` and `bedrock_region` settings. Changed `llm_max_tokens` default from `250` to `500` (see "Behavior differences" below). |
| `backend/app/llm/factory.py` | This is the one place in the app that turns a config value (`LLM_PROVIDER=...`) into an actual provider object. Removed the Groq branch, kept only the Bedrock branch. |
| `backend/.env.example` | Removed the `GROQ_API_KEY=` line. Updated the comments to explain Bedrock uses AWS credentials, not an API key in this file. Updated `LLM_MAX_TOKENS` from `250` to `500`. |
| `backend/requirements.txt` | Unrelated to Groq/Bedrock directly, but fixed alongside this work: `pymongo` was pinned to `4.17.0`, which conflicts with another dependency (`langgraph-checkpoint-mongodb`) that requires `pymongo<4.17` — a clean install would fail. Re-pinned to `4.16.0`, the version already installed and working. |
| `backend/app/db/schema_definitions.py` | One comment updated (example value `"groq"` → `"bedrock"` in a field description). No behavior change. |
| `backend/app/rag/pipeline.py` | One historical comment left as-is describing a past measurement done against Groq — kept because it's an accurate record of why a setting was chosen, not a claim about what's active now. |
| `backend/loadtest/locustfile.py` | Comment updated to say "real Bedrock call latency" / "AWS credentials configured" instead of the old Groq-specific wording. No test logic changed. |
| `backend/tests/test_llm_provider.py` | Groq-specific tests removed (see "Files deleted" — the tests, not the file, since this file also covers provider-independent things). What's left: tests for the fake test-double provider and the LLM-based intent classifier, neither of which are Groq- or Bedrock-specific. |
| `backend/tests/test_llm_factory.py` | Groq-specific tests removed; two new tests added confirming the factory correctly builds a `BedrockProvider` when configured, and falls back safely if Bedrock config is broken. |
| `backend/tests/test_llm_usage_repository.py`, `test_llm_usage_tracking.py`, `test_api_usage.py` | These test a generic "record LLM token usage" feature that isn't tied to any specific provider — they just needed *some* provider name and model name as example data. Updated the example values from `"groq"` / `"llama-3.3-70b-versatile"` to `"bedrock"` / `"openai.gpt-oss-120b-1:0"` so the test suite doesn't reference a provider that no longer exists. |
| `docs/phase-2-architecture/adr/002-llm-strategy-pattern.md` | The architecture decision record for "make the LLM provider swappable" — updated to record that the provider has now changed twice (DeepSeek was the original plan, Groq was a free-tier stand-in, Bedrock is current), and that each swap really was just a config change, which is the whole point this record exists to justify. |
| `docs/phase-12-testing/testing.md` | The existing Groq write-up was kept as a historical record (clearly labeled as history, not current state) and a new section was added documenting the Bedrock verification: the side-by-side comparison against the Groq baseline, and the token-budget re-measurement. Details in the sections below. |
| `docs/folder-structure.md` | The table describing what's in `app/llm/` updated to list `bedrock.py` and `usage.py` instead of `groq.py` and `openai_compatible.py`. |

---

## Files deleted, and why each was safe

| File | Why it was safe to delete |
|---|---|
| `backend/app/llm/providers/groq.py` | The Groq adapter. Safe to delete because nothing else in the codebase imports it directly by design — the whole point of the provider-interface pattern (ADR 002) is that callers only ever depend on the generic interface, never a specific provider. Confirmed by search: no remaining imports anywhere. |
| `backend/app/llm/providers/openai_compatible.py` | Shared HTTP logic that Groq's adapter was built on top of (for calling any "OpenAI-style" HTTP API). Once Groq was deleted, this had exactly zero remaining users — Bedrock talks to AWS over `boto3`, not HTTP, so it doesn't use this file. Confirmed nothing else imported it before deleting; keeping unused code around was the actual risk, not removing it. |
| `backend/tests/test_llm_usage_real_groq.py` | A test that made a real, live call to Groq's API to confirm token-usage tracking worked end-to-end. Once `GroqProvider` no longer exists, this test can't run — the equivalent coverage for Bedrock exists via `test_bedrock_provider.py` (usage parsing) and `test_max_tokens_real_bedrock.py` (real calls). |
| `backend/tests/test_max_tokens_real_groq.py` | A test that made repeated real Groq calls to check answers weren't getting cut off (truncated). Directly replaced by `test_max_tokens_real_bedrock.py`, which does the same job for Bedrock — and had to be re-measured anyway, since the safe token limit is different for the new model (see below). |

Before any of this deletion happened, both providers were run through the same test suite and
the same real-data comparison (golden-set eval, described below) to confirm Bedrock was a solid
replacement — Groq wasn't removed until that evidence was in hand.

---

## Config / environment changes

**Removed:**
- `GROQ_API_KEY` — no longer read anywhere, removed from `.env.example`. (If your local `.env`
  still has this line, it's harmless — unknown settings are silently ignored — but you can
  delete it.)
- `llm_provider=groq` as a valid option — `"groq"` is no longer a recognized value for
  `LLM_PROVIDER`.

**Added:**
- `bedrock_model_id` (default `openai.gpt-oss-120b-1:0`) and `bedrock_region` (default
  `us-east-1`) — which model and AWS region to call. Both have sensible defaults, so nothing
  needs to be set for a normal setup.

**The important behavioral difference: where credentials live.**
Groq's API key lived in `.env` (`GROQ_API_KEY=...`) — a plain secret string in a file. Bedrock
does **not** read any credential from `.env` or from application config at all. Instead, the
Bedrock adapter uses AWS's own standard credential lookup (via `boto3`), which checks, in order:
your local `~/.aws/credentials` file, environment variables, or an IAM role if running inside
AWS (e.g. on EC2/ECS in production). This means:
- There is no AWS secret key sitting in this repo or in `.env` — a deliberate security
  improvement over how the Groq key was handled.
- Running this locally requires AWS credentials to be set up on your machine separately (`aws
  configure`, or environment variables) — it's not enough to just fill in `.env` anymore.
- In production, this is normally handled by attaching an IAM role to whatever's running the
  app, so no credential file is needed there either.

---

## Behavior differences a user would actually notice

**1. Internal "thinking" text is now hidden.**
gpt-oss (the Bedrock model) generates its answer in two parts: first a block of internal
reasoning/scratch-work (wrapped in `<reasoning>...</reasoning>`), then the actual answer.
Llama-3.3 on Groq didn't do this — it went straight to the answer. The Bedrock adapter strips
the reasoning block out before the response ever reaches the chat pipeline, so end users only
ever see the final answer, same as before. This is invisible in normal use, but it's worth
knowing it's happening, because it affects the next point directly.

**2. The token budget per answer was raised from 250 to 500.**
`llm_max_tokens` is a cap on how much text the model is allowed to generate per answer, mainly
there to control cost and response time. The old value (250) was tuned specifically for
Llama-3.3 on Groq. It's now 500. Reason: that hidden reasoning block from point 1 above isn't
free — the model spends real generation budget on it *before* it even starts writing the
visible answer. So the same 250-token cap that safely fit Llama's full answers before now only
leaves a much smaller leftover budget for gpt-oss's visible answer, and answers were getting cut
off mid-sentence.

This wasn't theoretical — it was measured with repeated real calls against the longest realistic
answer in the test set (a device-troubleshooting question):

| Token cap | Real repeated calls | How often the answer got cut off |
|---|---|---|
| 250 (old default) | 3 | 3 out of 3 |
| 350 | 6 | 1 out of 6 |
| 400 | 6 | 1 out of 6 |
| 450 | 6 | 0 out of 6 |
| **500 (new default)** | 12 | **0 out of 12**, with comfortable headroom |

500 was chosen because it cleared every real test with margin to spare, not just barely. A user
should notice fewer (ideally zero) answers that trail off mid-sentence compared to if the old
250 cap had been kept with the new model.

**3. Everything else is the same.**
Response format, citations, which intents get real generated answers vs. a template response,
error/fallback behavior when the LLM is unavailable — none of that changed. The provider swap
was designed to be invisible except for the two points above.

---

## Test suite: before and after

- **Before Groq removal:** 520 tests passing (with live Groq and live Bedrock credentials both
  available in that environment, including the opt-in real-API tests for both).
- **After Groq removal:** 507 tests passing. The drop of 13 is entirely accounted for by
  deliberate removal, not lost coverage:
  - 2 whole test files deleted (7 tests: 6 in the max-tokens file, 1 in the usage-tracking file)
    that only made sense against a real Groq account, which no longer exists as a supported
    provider.
  - 6 Groq-specific unit tests removed from `test_llm_provider.py` and `test_llm_factory.py`
    (request-building, default model/URL, HTTP-error handling, factory dispatch) — each has a
    direct Bedrock equivalent in `test_bedrock_provider.py` / `test_llm_factory.py`'s new
    Bedrock tests, so this is a like-for-like swap, not a coverage loss.
  - Net new: 13 new Bedrock-specific tests were added (`test_bedrock_provider.py`'s 13 tests)
    covering things Groq's tests never had to cover — the reasoning-block stripping and its
    defensive fallback.
- In an environment where AWS credentials aren't currently loaded (as happened later in this
  session, when only a restricted `ai-intern` AWS identity was available), the 6 opt-in
  real-Bedrock tests in `test_max_tokens_real_bedrock.py` skip themselves cleanly rather than
  failing — by design, matching how the old Groq real-call tests behaved when no API key was
  configured.

## Golden-set comparison: Bedrock vs. Groq

The project has a standing 45-case evaluation set covering every supported intent, scored on
four metrics: intent-classification accuracy, entity-extraction accuracy, retrieval precision,
and citation groundedness (whether the sources cited in an answer are actually the right
sources). This was run once against real Groq and once against real Bedrock:

| Metric | Groq / Llama-3.3 | Bedrock / gpt-oss-120b |
|---|---|---|
| Intent accuracy | 100.0% | 100.0% |
| Entity accuracy | 100.0% | 100.0% |
| Retrieval precision | 100.0% | 100.0% |
| Citation groundedness | 100.0% | 100.0% |

**Important context on why these are identical, not just "both good":** this project's intent
classification doesn't use the LLM at all by default (it's rule-based), and citation
groundedness is checked against which source documents were *retrieved and given to* the model,
not anything parsed out of the model's written answer. So these four numbers were never capable
of detecting a difference between the two providers, by design — the golden-set was already
known (and documented) to behave this way before this migration. What the run *did* confirm
with real evidence: all real calls to Bedrock completed successfully with no errors, matching
Groq's reliability. A genuine side-by-side comparison of answer *quality* (not just correctness
of the surrounding pipeline) would need human or model-graded review of the written answers
themselves, which this test suite doesn't attempt for either provider.
