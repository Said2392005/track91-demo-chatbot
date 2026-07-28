# Chunk Metadata Schema — Phase 4

Every chunk written to ChromaDB (Phase 5) carries this metadata dict alongside its embedding
and text. ChromaDB metadata values must be primitive (str/int/float/bool) — no nested objects —
so this schema is intentionally flat.

| Field | Type | Source | Description |
|---|---|---|---|
| `chunk_id` | string | computed | `{doc_id}::{slugify(section_title)}[::{n}]` — see chunking-strategy.md. Also the ChromaDB record ID. |
| `doc_id` | string | front-matter | Stable source-document identifier, e.g. `"gps-device-offline-troubleshooting"`. |
| `title` | string | front-matter | Document title, e.g. `"GPS Device Offline Troubleshooting"`. |
| `category` | string (enum) | front-matter | One of `feature_guide`, `app_faq`, `troubleshooting`, `policy`, `pricing` — identical enum to `documents_meta.source_type` (Phase 3). |
| `section_title` | string | derived | The h2 heading text (or FAQ question text) this chunk came from. |
| `doc_version` | string | front-matter (`version`) | e.g. `"v1"`, `"v3-approved"`, `"draft-2026-06"`. |
| `approved_pricing` | bool | front-matter | Propagated unchanged from the document. **Only this field gates the `PRICING` intent** (Phase 7) — `category == "pricing"` alone is not sufficient, since an unapproved pricing doc must never answer a pricing question. |
| `chunk_index` | int | computed | Position of this chunk within its document (stable ordering for citation display); `0` unless the oversized-section fallback split a section into multiple chunks. |
| `content_hash` | string | computed | SHA-256 of the chunk's own text. Lets Phase 5 skip re-embedding unchanged chunks on re-ingestion. |
| `source_path` | string | ingestion | Relative path to the source file, e.g. `"kb_sources/pricing/track91-pricing-sheet-v3.md"` — for debugging/traceability, not shown to end users. |
| `ingested_at` | string (ISO 8601) | ingestion | Timestamp of the ingestion run that (last) wrote this chunk — set by Phase 5 at ingestion time, not authoring time. |

## Relationship to `documents_meta` (Phase 3, MongoDB)

`documents_meta` is the **document-level** registry (one row per source document);
this chunk metadata is **chunk-level** (many rows per document, living in ChromaDB). Phase 5's
ingestion script is responsible for keeping them in sync: for each source file, it
upserts one `documents_meta` row (keyed on `title` + `version`, per Phase 3's unique index)
*and* upserts that document's chunks into ChromaDB — both derived from the same front-matter,
so they can't drift out of sync by construction. `documents_meta.chunk_count` is updated to the
number of chunks produced for that document on each ingestion run.

## Why `approved_pricing` lives on every chunk, not just the pricing ones

Every chunk gets this field (defaulting to `false` for non-pricing categories) rather than only
pricing chunks having it, so the Phase 7 Context Assembler can apply one uniform filter
(`approved_pricing == true`) when assembling context for a `PRICING`-routed query without a
category branch — simpler and harder to get wrong than "check this field, but only if category
is pricing."
