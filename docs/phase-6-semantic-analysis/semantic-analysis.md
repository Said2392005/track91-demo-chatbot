# Semantic Analysis — Phase 6

## Objective

Turn a raw user utterance into (intent, entities), per the Phase 1 taxonomies: intent
classification, entity extraction (including the `vehicle_ref` normalization rule locked into
the Phase 2 sequence diagrams), and coreference resolution. This is the first phase to produce
LLM-consuming code — the `LLMProvider` interface from ADR 002 gets a real implementation here,
since LLM-based intent classification is its first consumer.

## Classifier strategy: hybrid (confirmed with the user before building)

Two strategies behind one `IntentClassifier` interface, selected by
`settings.intent_classifier_strategy`:

- **`RuleBasedIntentClassifier`** (default) — pattern/keyword scoring across all 31 intents,
  fully offline, no API key or network access needed. This is what's tested (161 paraphrase
  cases) and what ships as the default.
- **`LLMIntentClassifier`** — same interface, backed by `LLMProvider.generate()`, constrained
  to return one label from the fixed intent set. Not exercised against a live provider in this
  build (no credentials configured); tested against `FakeLLMProvider` to verify prompt
  construction and response parsing (including tolerating a JSON-wrapped reply).

Both are real, swappable via config — not a placeholder for one and a stub for the other.

## `LLMProvider` interface (ADR 002), implemented for the first time

- `app/llm/base.py` — the `LLMProvider` ABC, `Message`, `LLMResponse`.
- `app/llm/providers/deepseek.py` — real HTTP adapter (OpenAI-compatible `/chat/completions`),
  the roadmap's default cheap dev model. Request/response handling verified with
  `httpx.MockTransport` (request construction, auth header, response parsing, HTTP-error
  propagation) — not against the live API, since no `DEEPSEEK_API_KEY` is configured in this
  environment.
- `app/llm/providers/fake.py` — `FakeLLMProvider`, a deterministic test double, explicitly not
  a runtime option.
- `app/llm/factory.py` — `get_llm_provider()`, config-driven, matching the strategy-pattern ADR.

## Entity extraction and coreference

- `app/nlu/normalization.py` — the actual code for the normalization rule that, until now, only
  existed as prose in `entity-taxonomy.md` and a note in the Phase 2 sequence diagrams: strip →
  uppercase → remove separators → validate against the plate regex.
- `app/nlu/entity_extractor.py` — orchestrates plate/nickname resolution (via new minimal
  repositories, see below), driver-name resolution with collision detection, the date-range
  parser, dictionary lookups (`alert_type`, `metric_type`, `report_type`, `plan_tier_ref`), and
  coreference fallback — all driven by `app/core/taxonomy.py`'s per-intent required/optional
  entity table (transcribed from `intent-taxonomy.md`, the single source of truth Phase 9's
  router will also use).
- `app/nlu/coreference.py` — resolves pronouns against **passed-in** active-entity state only;
  it owns no storage. Persisting that state across turns is explicitly Phase 8's job, per
  `entity-taxonomy.md`'s own note — this phase only had to get the resolution algorithm right.
- `app/nlu/date_parser.py` — rule-based relative/absolute date range parsing ("yesterday",
  "last week", "last N days", ISO/day-month-year dates, explicit ranges).
- `app/nlu/pipeline.py` — combines classify → extract → the `CLARIFICATION_NEEDED` decision.
  This decision is deliberately **not** inside the classifier: from text alone, "what's its
  speed?" unambiguously means `GET_VEHICLE_SPEED` — it only becomes a clarification case once
  entity resolution fails to find an active vehicle for "its" to resolve against. Matches
  `intent-taxonomy.md`'s own note that this intent depends on more than the raw utterance.

### New minimal repositories (`app/db/repositories/`)

Phase 2's ADR 001 established the repository pattern; Phase 3 built the schema but no
repository classes yet. Entity resolution needs real lookups (plate → vehicle, name → driver),
so this phase adds `VehicleRepository`, `DriverRepository`, `GeofenceRepository` — company_id
required on every method (ADR 004), only these modules import `motor`. These are not final:
Phase 9 will extend the same classes with the query/write methods its tools need.

## Bugs found and fixed while building this phase

Three real bugs surfaced by writing and running tests against real data (not by inspection):

1. **Classifier substring-matching bug.** `_score()` originally checked trigger phrases with
   naive `in` substring containment — so the `"hi"` trigger for `GREETING` matched *inside*
   unrelated words: `"veHIcles"`, `"tHIs"`, `"anytHIng"`, `"DelHI"`. Caught by the paraphrase
   test suite (multiple unrelated utterances misclassified as `GREETING`). Fixed by switching
   to word-boundary regex matching for every phrase.
2. **Two over-broad classifier regexes, then an over-correction.** `EXPLAIN_FEATURE`'s
   `"how does .+ work"` and `EXPLAIN_ALERT_TYPE`'s optional-alert `"what does .+ (alert )?mean"`
   both swallowed `GENERAL_KNOWLEDGE`-shaped questions ("how does GPS triangulation work?",
   "what does AIS-140 mean?"). The first fix — scoping `EXPLAIN_FEATURE` to a fixed list of
   named-feature regexes and making "alert" mandatory in `EXPLAIN_ALERT_TYPE` — over-corrected:
   it passed all 161 original paraphrase tests but failed realistic rephrasings never in that
   set ("Can you tell me how geofencing works?", "What's geofencing?", "Can you explain what the
   panic alert means?" all fell through to `GENERAL_KNOWLEDGE`/`OUT_OF_SCOPE`). Caught by testing
   against a broader paraphrase set beyond the originally-motivating examples before committing,
   per explicit request. Fixed by replacing both fixed patterns with a `TRIGGER_COOCCURRENCE`
   check (`app/nlu/trigger_patterns.py`): score if the utterance contains an explanation-verb
   phrase ("how does", "what's", "explain", "tell me", "used for", ...) **and** a known
   feature/alert-type keyword, anywhere in the utterance, in any order — not a fixed sentence
   shape. Verified against 20 cases spanning both directions (10 realistic rephrasings that must
   match, 4 general-knowledge controls that must not, plus 2 sanity checks against unrelated
   intents) with zero mismatches, and the 4 generalization-motivated cases are now permanent
   regression tests in `test_intent_classifier.py`, not just an ad-hoc check.
3. **Real Phase 3 index bug, not just a test-data mistake.** `vehicles.company_device_unique`
   and `drivers.company_license_unique` were declared `sparse: True` on **compound** keys
   `(company_id, device_id)` / `(company_id, license_number)`. MongoDB's compound-sparse
   semantics only skip a document if *all* indexed fields are missing — since `company_id` is
   always present, a document merely missing `device_id` (a legitimate state: per
   `kb_sources/app_faq/track91-app-faq.md`, a vehicle can exist before a GPS device is
   registered to it) still gets indexed with `device_id: null`, so a second such vehicle at the
   same company collided on a false duplicate-key error. Fixed both indexes to use
   `partialFilterExpression: {field: {"$exists": True}}` instead of `sparse`, which correctly
   excludes documents missing that specific field regardless of what else is present. This is a
   correctness fix to already-committed Phase 3 code — flagging in case a real Mongo instance
   with the old index definition already exists anywhere (a live one would need the index
   dropped and recreated; `create_index` does not alter an existing same-named index in place).

## Testing

**271/271 tests passing** (51 from Phases 3/5 + 220 new), run against real MongoDB — no mocks
for data access:

| File | Coverage |
|---|---|
| `test_intent_classifier.py` | 175 cases: 5+ realistic paraphrases (not trigger-phrase copies) per intent across all 29 text-triggered intents, `AFFIRM_DENY` dialogue-state gating, plus 14 `EXPLAIN_FEATURE`/`EXPLAIN_ALERT_TYPE` generalization regressions (see bug #2) |
| `test_entity_extractor.py` | Malformed/partial input: lowercase/spaced/dotted plates, unknown-but-valid plates, cross-tenant non-resolution, driver name collisions, missing required entities, empty/garbled input, pronoun resolution with/without active state |
| `test_coreference.py` | Pronoun detection and active-entity resolution, unit-level |
| `test_date_parser.py` | Relative/absolute date expressions, explicit ranges, malformed/vague input returning `None` |
| `test_llm_provider.py` | `DeepSeekProvider` request/response handling via `httpx.MockTransport`; `LLMIntentClassifier` via `FakeLLMProvider` |
| `test_pipeline.py` | The `CLARIFICATION_NEEDED` decision end-to-end |

Paraphrases were run against the classifier first, not written to match the code — 14 of the
initial 161 failed on the first pass, each traced to a specific gap (missing phrase variant,
word-order mismatch, plural form, contraction) and fixed in `trigger_patterns.py` rather than
softened test assertions.
