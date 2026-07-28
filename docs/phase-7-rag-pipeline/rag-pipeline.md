# RAG Pipeline — Phase 7

## Objective

Turn (`kb_topic`, `category`) from Phase 6 into a cited answer: retrieve top-k from ChromaDB
(Phase 5) → re-rank with a self-hosted cross-encoder → assemble context (gated for `pricing`)
→ generate via the `LLMProvider` interface (Phase 6) — or skip generation entirely and return a
fixed fallback for the two ungenerateable cases.

## Components (`backend/app/rag/`)

- `reranker.py` — `cross-encoder/ms-marco-MiniLM-L-6-v2`, same self-hosted sentence-transformers
  family as the Phase 5 embedding model, no new dependency, no external API. Returns
  `RankedChunk` — a distinct type from `RetrievedChunk`, not a repurposed field, because
  embedding *distance* (lower = more similar) and cross-encoder *relevance score* (higher = more
  relevant) point in opposite directions; reusing one field for both was a near-miss caught
  before committing (see design notes below).
- `context_assembler.py` — formats chunks into a citable context block. Owns the `PRICING` gate:
  `assemble_pricing_context()` filters to `approved_pricing: true` **before** any rank-based
  `top_n` truncation, and returns `None` if nothing survives — filtering after truncation would
  let a top-ranked unapproved chunk silently displace an approved one within the cutoff.
- `generation.py` — cited generation via `LLMProvider.generate()`. Only ever sees
  already-assembled, already-gated context.
- `fallback.py` — two fixed strings (`PRICING_NO_APPROVED_DOC_RESPONSE`,
  `NO_RELEVANT_CONTENT_RESPONSE`), not LLM-generated.
- `pipeline.py` — `answer_kb_query()`, the orchestrator. For the two fallback branches,
  `generate_cited_answer()` is not in the code path at all — not "prompted to refuse," literally
  absent from execution — matching the Phase 2 sequence diagram's "LLMProvider is never called
  with unapproved context for a PRICING-shaped query."

## The `PRICING` gate, verified end to end

Three layers of proof, not just a written rule:

1. **Unit level** (`test_context_assembler.py`) — an unapproved chunk scoring *higher* than an
   approved one still gets filtered out before `top_n` truncation.
2. **Pipeline level, isolated collection** (`test_pricing_no_approved_doc_at_all_never_calls_llm`)
   — a collection containing only unapproved chunks: `llm_invoked` is `False`,
   `FakeLLMProvider.received_calls` is empty, the answer is the exact fixed string.
3. **Pipeline level, real KB** (`test_pricing_ambiguous_query_only_ever_uses_approved_content`)
   — see the correction below: this is where a wrong assumption from Phase 4/5 got caught.

### Correction to the Phase 4/5 "no-approved-doc" scenario

`docs/phase-4-knowledge-base/source-inventory.md` originally assumed the *"1,000+ vehicles"*
query would retrieve *only* the unapproved draft doc, triggering the full zero-LLM-call
fallback. Building and testing the real pipeline against the real KB showed this was wrong: the
KB only has 9 pricing chunks total (5 approved + 4 unapproved), so top-k retrieval for this
query always surfaces at least one approved chunk too — here, the approved sheet's own "contact
sales for custom volume pricing above 500 vehicles" guidance, which is a correct, non-
hallucinated answer. Verified empirically: the unapproved draft chunk ranks **#1** by raw
embedding distance for this query, ahead of every approved chunk — and still never appears in
the generated answer's citations, because the filter runs before truncation regardless of rank.
The property that actually matters (unapproved content never reaches generation) holds; the
narrower claim (this exact query hits the full fallback) didn't, and the doc and test now say
so instead of quietly forcing the original assumption to pass. The pure fallback is real and
tested — just via an isolated collection, since that's the only way to deterministically
produce zero approved candidates against a KB this small.

## Design notes

- `RankedChunk` vs `RetrievedChunk.distance`: caught before committing that `dataclasses.replace()`
  to overwrite `.distance` with a cross-encoder score would leave two completely different
  metrics (lower-is-better vs. higher-is-better) sharing one field name and type — a defined
  `RankedChunk.relevance_score` avoids that ambiguity for anyone reading the code later.
- Non-`pricing` categories use `assemble_context()` (no approval filter) — the filter is
  `pricing`-specific because it's the only category where an unapproved *source* exists in this
  KB at all (see Phase 4's `documents_meta` design; every other category's docs are all
  effectively "approved" by virtue of being published to the KB).

## Testing

**37 new tests, 308/308 total passing** (271 carried forward) — includes 2 tests added when
re-ranking became opt-in (`test_reranking_is_off_by_default`,
`test_reranking_can_be_explicitly_enabled`, both in `test_rag_pipeline.py`, spying on
`app.rag.pipeline.rerank` to prove it's genuinely not called by default rather than just
happening to produce a correct-looking answer either way):

| File | Coverage |
|---|---|
| `test_reranker.py` | Ordering, empty input, `top_n`, metadata preservation |
| `test_context_assembler.py` | The `PRICING` gate's filter-before-truncate property, non-pricing pass-through |
| `test_retrieval_precision.py` | precision@3 on the 16-query golden set, both retrieval-only and post-rerank |
| `test_rag_pipeline.py` | End-to-end via `FakeLLMProvider`, asserting `llm_invoked` and call counts, not just returned text |

### Retrieval precision@k — real numbers, thresholds set from them

Measured against the 16-query golden set (`tests/golden_sets/rag_golden_set.py`, 3 queries per
KB category + 1 for the unapproved doc specifically):

- Average retrieval-only precision@3: **0.9375**
- Average precision@3 after cross-encoder re-ranking: **0.875**

Re-ranking does not universally improve precision@k on a KB this small — on a couple of short,
topically-adjacent documents it pulls in a chunk from a neighboring doc. Its value in this
pipeline is context/citation ordering quality within the already-gated candidate set, not
solving the `PRICING` approved/unapproved distinction, which the explicit metadata filter
handles independent of rank. Test thresholds (`>= 0.85` retrieval, `>= 0.80` reranked) were set
with real margin below these measured numbers, not picked to make the test pass.

## Decision: re-ranking is opt-in, disabled by default

`settings.rag_use_reranker` defaults to `False` (`app/core/config.py`). Given the measured
numbers above — re-ranking *reduced* precision@3 on this KB (0.9375 → 0.875), while adding a
second model's load-and-inference cost to every KB query — there was no case for keeping it on
by default:

- **No quality argument.** It measured worse, not better, at the current KB size (28 chunks,
  6 documents). There's nothing to trade latency against.
- **No correctness argument.** The `PRICING` gate's safety property (unapproved content never
  reaches generation) is enforced by `context_assembler.py`'s explicit `approved_pricing`
  filter, which runs identically regardless of whether the input candidates are ranked by raw
  embedding distance or by cross-encoder score — proven directly by
  `test_pricing_gate_filters_out_unapproved_even_when_it_ranks_highest` (retrieval-only ranking)
  and the pipeline-level pricing tests (also retrieval-only ranking by default, since re-ranking
  is off). Disabling the default does not weaken the gate.
- **A real cost argument.** At pilot scale (<50 concurrent, per `non-goals.md`), loading and
  running a second CPU model on every KB-routed turn is pure overhead with the measurements
  above showing no offsetting benefit.

`answer_kb_query()` still accepts `use_reranking: bool | None` as an explicit per-call override
(`None` defers to `settings.rag_use_reranker`), and `context_assembler.py` accepts either
`RetrievedChunk` (raw retrieval) or `RankedChunk` (post-rerank) unchanged, via a `ScoredChunk`
structural protocol — so flipping the default later, once the KB is large/heterogeneous enough
that topical overlap between documents becomes a real retrieval problem, is a one-line config
change, not a code change. Re-measure precision@k against the golden set before flipping it,
the same way this decision was made — don't re-enable on the assumption that a bigger KB
automatically makes re-ranking pay for itself.
