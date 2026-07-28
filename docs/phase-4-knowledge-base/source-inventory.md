# Source Inventory — Phase 4

Synthetic KB for a standalone build with no real Track91 documentation available (per
`docs/phase-1-planning/non-goals.md` — all data in this build is mocked). All 6 source files
live under `backend/kb_sources/<category>/`, one subfolder per `category`
(== `documents_meta.source_type`), ready for Phase 5 to chunk and embed.

> **Relationship to Phase 3's `documents_meta` seed data:** the seed script
> (`backend/app/db/seed_data.py`) inserted 6 placeholder `documents_meta` rows to exercise the
> Mongo schema before any real KB content existed. These source files are the real content;
> Phase 5's ingestion script is what actually upserts `documents_meta` from each file's
> front-matter (keyed on `title` + `version`, per the Phase 3 unique index), which will
> supersede the placeholder rows rather than duplicate them.

## Inventory

| File | `doc_id` | `category` | `version` | `approved_pricing` | Chunks (estimated) |
|---|---|---|---|---|---|
| `troubleshooting/gps-device-offline.md` | `gps-device-offline-troubleshooting` | `troubleshooting` | `v1` | `false` | 4 |
| `app_faq/track91-app-faq.md` | `track91-app-faq` | `app_faq` | `v1` | `false` | 6 (one per Q/A pair) |
| `policy/data-retention-policy.md` | `data-retention-policy` | `policy` | `v1` | `false` | 5 |
| `feature_guide/geofencing-feature-guide.md` | `geofencing-feature-guide` | `feature_guide` | `v1` | `false` | 4 |
| `pricing/track91-pricing-sheet-v3.md` | `track91-pricing-sheet` | `pricing` | `v3-approved` | **`true`** | 5 |
| `pricing/enterprise-pricing-draft-notes.md` | `enterprise-pricing-draft-notes` | `pricing` | `draft-2026-06` | **`false`** | 4 |

**28 chunks total**, following the rules in `chunking-strategy.md` (h2-section chunking for
everything except `app_faq`, which chunks per Q/A pair).

## Coverage against the Phase 1 intent taxonomy

| KB intent (intent-taxonomy.md) | Covered by |
|---|---|
| `EXPLAIN_FEATURE` | `geofencing-feature-guide.md` |
| `APP_FAQ` | `track91-app-faq.md` |
| `TROUBLESHOOTING_DEVICE` | `gps-device-offline.md` |
| `POLICY_QUESTION` | `data-retention-policy.md` |
| `PRICING` | both pricing docs (see gate test cases below) |
| `GENERAL_KNOWLEDGE` | intentionally **no** source doc — this intent is explicitly never backed by the KB |

## `PRICING` gate test cases (for Phase 7)

The two pricing documents are deliberately authored so retrieval alone can't tell them apart by
topic — only `approved_pricing` distinguishes what's answerable:

1. **Approved-doc-exists case.** A query like *"How much does the Pro plan cost?"* or *"What's
   the Starter plan price?"* retrieves chunks from `track91-pricing-sheet-v3.md`
   (`approved_pricing: true`). The gate passes; the LLM generates a cited answer with the
   approved figure.
2. **No-approved-doc case — corrected after Phase 7 implementation testing.** The original
   assumption here was that a query like *"What's your rate for 1,000+ vehicles?"* retrieves
   *only* a chunk from `enterprise-pricing-draft-notes.md`, triggering the full fallback. Built
   and tested against the real pipeline (Phase 7), this turned out to be wrong: the KB only has
   9 pricing chunks total (5 approved + 4 unapproved), so top-k retrieval for this query always
   surfaces at least one approved chunk too — here, the approved sheet's own "contact sales for
   custom volume pricing above 500 vehicles" guidance, which is a genuinely correct, non-
   hallucinated answer to the question. What actually matters — and is what's tested — is
   narrower and still holds: **the unapproved draft chunk, even when it ranks #1 by raw
   embedding distance (verified empirically), never reaches generation.** Every citation traces
   back only to the approved sheet. The *pure* zero-approved-chunk fallback (no LLM call at
   all) is real and tested (`test_pricing_no_approved_doc_at_all_never_calls_llm`,
   `backend/tests/test_rag_pipeline.py`), just not reachable via this specific query against
   this specific small KB — it's tested against an isolated collection containing only the
   unapproved doc instead, which is the honest way to exercise that branch deterministically.

Both cases should be added to Phase 7's precision@k golden set and Phase 12's eval harness as
explicit `PRICING`-intent test rows, since this is the one place in the whole system where
"retrieval succeeded" and "answerable" are deliberately different questions.

### Hard requirement for Phase 7, confirmed necessary by Phase 5 testing

Phase 5's retrieval smoke test measured the actual embedding distance between these two cases'
top candidates for the no-approved-doc query and found them **0.005 apart** (0.7398 vs 0.7449 —
see `docs/phase-5-embedding-pipeline/embedding-pipeline.md`). Similarity rank is not a reliable
signal for which pricing chunk is approved; the two are near-indistinguishable by embedding
distance alone.

**Therefore: for any `category: pricing` retrieval, Phase 7 must never select the pricing chunk
to answer from by similarity rank.** The required logic is:

1. Retrieve top-k candidates as normal.
2. Filter the candidate set to `approved_pricing: true` chunks only.
3. If the filtered set is non-empty, assemble context and generate from it (the approved-doc-exists
   case).
4. If the filtered set is empty — even if unapproved chunks were retrieved and ranked highly —
   treat this as the no-approved-doc case and return the fixed contact-support response,
   exactly as shown in [sequence diagram #4](../phase-2-architecture/sequence-diagrams.md).
   The LLM must never be invoked with an unapproved chunk in its context for a `PRICING`-routed
   query.

This is a hard requirement, not a tuning suggestion — top-1-by-distance is actively wrong here,
since the empirical margin between "answerable" and "must fall back" is smaller than normal
embedding noise.

## Word/format notes

- All source docs are hand-authored Markdown with YAML front-matter (see
  `chunking-strategy.md`) — no PDFs in this synthetic set, though Phase 5's ingestion should
  still support PDF input per the roadmap's stated pipeline (PDF/doc → chunks → ChromaDB) for
  when real documents arrive later.
- Every file stays well under the ~500-word oversized-section fallback threshold per section, so
  none of the estimated chunk counts above are expected to split further at ingestion time.
