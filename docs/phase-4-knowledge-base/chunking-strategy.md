# Chunking Strategy — Phase 4

## Principle: structural chunking, not fixed-size windows

Chunks are cut along the document's own structure (Markdown headings, FAQ Q/A boundaries), not
by a fixed token-count sliding window with overlap. Track91's KB source material is short,
well-structured operational content (guides, FAQs, policy, pricing) where a heading or a
question already marks a coherent, self-contained unit of meaning — token-window chunking would
routinely cut a step-by-step fix or a Q/A pair in half for no benefit.

## Source format

Every source file is Markdown with a YAML front-matter block carrying doc-level metadata:

```markdown
---
doc_id: gps-device-offline-troubleshooting
title: GPS Device Offline Troubleshooting
category: troubleshooting
version: v1
approved_pricing: false
---

## Overview
...

## Common Causes
...
```

`doc_id`, `category` (== `documents_meta.source_type`), `version`, and `approved_pricing` are
required front-matter fields — Phase 5's ingestion script fails loudly if any are missing,
rather than guessing a default (a document with no `approved_pricing` field must not silently
become eligible for the `PRICING` gate).

## Chunking rules, by category

1. **Default rule (`feature_guide`, `troubleshooting`, `policy`, `pricing`):** split on `##`
   (h2) headings. Each h2 section is one chunk, with the heading text captured as
   `section_title`. `###` (h3) subheadings do **not** start a new chunk — they stay nested
   inside their parent h2 chunk, since splitting a fix's numbered sub-steps from its intro
   would strand context on either side.
2. **`app_faq` special case:** each Q/A pair is exactly one chunk, regardless of the default
   h2 rule. A Q/A pair is delimited as `## Q: <question>` through the next `## Q:` heading
   (or end of file); the question text becomes `section_title`. This is called out separately
   from rule 1 because splitting a question from its answer — or merging two unrelated
   questions into one chunk — directly breaks retrieval: the query is the question, so the
   question text must stay attached to the answer that resolves it.
3. **Oversized-section fallback:** if a chunk produced by rule 1 or 2 exceeds ~500 words
   (a soft ceiling, not a hard structural rule), split it further at paragraph boundaries
   (blank-line-separated), append `_1`, `_2`, ... to that chunk's `chunk_index`, and repeat the
   parent's `section_title` on every sub-chunk. This is a fallback for oversized content, not
   the primary chunking mechanism — it should rarely trigger given how short these source docs
   are.
4. **No cross-document merging, no overlap.** Each chunk's text comes from exactly one section
   of exactly one source document. No sliding-window overlap between adjacent chunks — since
   chunk boundaries already follow semantic structure, overlap would only introduce duplicate
   retrieval hits rather than preserve context.

## Chunk ID — stable and deterministic (idempotency requirement)

Per the roadmap's non-negotiable rule ("ChromaDB ingestion must be idempotent — stable chunk
IDs, upsert not insert"), every chunk's ID is computed, never generated (no random UUIDs):

```
chunk_id = f"{doc_id}::{slugify(section_title)}"          # rule 1/2, one chunk per section
chunk_id = f"{doc_id}::{slugify(section_title)}::{n}"     # rule 3, oversized-section fallback
```

Re-running ingestion on an unchanged source file recomputes the exact same chunk IDs, so
Phase 5's `upsert` (ChromaDB `collection.upsert(ids=..., ...)`) overwrites in place instead of
duplicating. A `content_hash` (SHA-256 of the chunk's own text, stored in chunk metadata) lets
Phase 5 skip re-embedding a chunk whose text hasn't changed since the last ingestion run, as a
performance optimization — not a correctness requirement, since `upsert` is already safe to
re-run unconditionally.

## What this phase does NOT decide

- The actual embedding model call and ChromaDB write — that's Phase 5.
- Retrieval top-k, re-ranking, or the `PRICING` gate's retrieval-time filter logic — that's
  Phase 7. This phase only guarantees the metadata (`approved_pricing`, `category`, etc.) that
  gate depends on is present and correct on every chunk.
