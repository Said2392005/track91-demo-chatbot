# Embedding Pipeline — Phase 5

## Objective

Turn the 28 chunks defined in `backend/kb_sources/` (Phase 4) into a queryable ChromaDB
collection: chunk (already done, Phase 4 rules) → embed (self-hosted, local) → upsert
(idempotent). Implemented as a standalone offline job, not inline in the API request path — the
chat request path (Phase 7+) only ever *queries* the already-populated collection.

## Model choice: `all-MiniLM-L6-v2`

Chosen over BGE-M3, per the roadmap's "your call on the tradeoff":

| | `all-MiniLM-L6-v2` | `bge-m3` |
|---|---|---|
| Size / dims | ~80MB, 384-dim | ~2GB, 1024-dim |
| CPU inference speed | fast | noticeably slower |
| Strengths | short, single-language text | multilingual, long-context (8k tokens), stronger retrieval on hard queries |

The KB (Phase 4) is short, English-only, operational text — no document exceeds ~800 words, and
the deployment target is a <50-concurrent pilot (per Phase 1 scope), often running on a laptop
or a small CPU instance in dev. BGE-M3's multilingual/long-context strengths address problems
this KB doesn't have, at several times the size and latency cost. `embedding_model_name` is a
config value (`app/core/config.py`), not hardcoded at call sites — swapping to `bge-m3` later
if KB content grows more complex is a config change, consistent with the LLM provider's
strategy-pattern precedent ([ADR 002](../phase-2-architecture/adr/002-llm-strategy-pattern.md)).

## Pipeline modules (`backend/app/kb/`)

- `chunker.py` — Phase 4's chunking rules (already built, unchanged this phase): parses
  front-matter, splits on `##` headings / FAQ Q/A pairs, computes stable `chunk_id` and
  `content_hash`.
- `embedder.py` — thin wrapper around `sentence_transformers.SentenceTransformer`; one
  `embed_texts()` function, model loaded once and cached (`lru_cache`).
- `chroma_client.py` — `PersistentClient` factory (`chroma_persist_dir` config) + collection
  getter (`kb_chunks`, cosine similarity space).
- `ingest.py` — the CLI job (`python -m app.kb.ingest`):
  1. Load + chunk all source files.
  2. For each chunk, compare against the existing chunk's stored `content_hash` in Chroma;
     only chunks that are new or changed get embedded.
  3. `collection.upsert(ids=..., ...)` — stable IDs mean this overwrites in place.
  4. Sync `documents_meta` in Mongo (one row per document, keyed on `title` + `version`) so the
     doc-level registry (Phase 3) and the chunk-level data (Chroma) can't drift apart — this is
     the same relationship documented in Phase 4's `metadata-schema.md`.
- `retrieve.py` — a deliberately minimal retrieval helper (embed query → Chroma top-k query).
  **Not** the Phase 7 RAG pipeline — no re-ranking, no context assembly, no `PRICING` gate
  enforcement. It exists so this phase's retrieval smoke test has something to call, and so
  Phase 7 has one query path to build on rather than a second reimplementation.

## Idempotency

Two mechanisms, and the tests to prove them ([`tests/test_kb_ingestion.py`](../../backend/tests/test_kb_ingestion.py)):

1. **Stable chunk IDs** (`{doc_id}::{slugified section_title}`, Phase 4) — re-ingesting an
   unchanged file recomputes identical IDs, so `upsert` overwrites rather than duplicates.
2. **`content_hash` short-circuit** — a chunk whose text hasn't changed since the last run is
   skipped entirely (not re-embedded, not re-upserted), which is a performance optimization on
   top of (1), not a substitute for it.

Verified: running `python -m app.kb.ingest` twice against the real 28-chunk KB produces
`{"embedded": 0, "skipped_unchanged": 28}` on the second run, `collection.count()` unchanged.
Also verified that editing one chunk's text and re-ingesting re-embeds only that one chunk and
still leaves `collection.count()` at 28 (upsert-in-place, not append).

## Cross-phase fix while wiring this up

Building `sync_documents_meta()` surfaced a real drift bug: two of Phase 3's seed placeholder
`documents_meta` rows didn't exactly match Phase 4's real KB source front-matter — a title
mismatch (`"How to Register a GPS Device"` vs the real `"Track91 App FAQ"`) and a version
mismatch (`"v2"` vs the real `"v1"` for the retention policy doc). Since those are upserted on
`(title, version)`, the mismatched placeholders would have been left behind as stale orphan
rows instead of being superseded, contradicting what Phase 4's `source-inventory.md` already
promised. Fixed by aligning `backend/app/db/seed_data.py`'s placeholder titles/versions to
match the real source docs exactly. Verified end-to-end: seeding then ingesting against the
same fresh database now produces exactly 6 `documents_meta` rows, not 8.

## Testing

```bash
cd backend
TEST_MONGO_URI="mongodb://127.0.0.1:27017" PYTHONPATH=. .venv/bin/python -m pytest tests/test_kb_ingestion.py tests/test_kb_retrieval_smoke.py -v
```

- **`test_kb_ingestion.py`** — chunk count (28) and ID uniqueness; ingestion run twice produces
  identical counts with zero re-embeds on the second run; editing a chunk upserts in place.
- **`test_kb_retrieval_smoke.py`** — one query per KB category, plus both `PRICING` gate cases
  from `source-inventory.md`:
  - *Approved-doc-exists* ("How much does the Pro plan cost per month?") → top hit is the
    approved pricing sheet, `approved_pricing: true`.
  - *No-approved-doc* ("What is your custom pricing rate for 1000+ vehicles?") → the unapproved
    draft doc is retrieved (proving the scenario is real and retrievable) alongside the
    approved sheet's Enterprise section — a genuinely close race (see below), which is exactly
    why this case exists: retrieval alone can't tell them apart, so Phase 7's gate has real
    work to do, checking `approved_pricing` rather than assuming "retrieved" means "approved."

Assertions use top-3/top-4 **membership**, not strict top-1 rank, calibrated against actual
model output rather than assumed — the FAQ "register a GPS device" query's exact chunk landed
at rank 2, and the two pricing chunks for the ambiguous >1000-vehicle query differ by a
similarity margin of ~0.005 (0.7398 vs 0.7449), too close to assert ordering on. Precision@k
and re-ranking quality are explicitly Phase 7's job against a larger golden set, not this
phase's.

**51/51 tests passing** (42 from Phase 3 + 9 new).
