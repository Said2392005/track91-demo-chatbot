# Non-Goals — Phase 1

Explicit scope boundaries for v1. Anything not on this list is presumptively in scope; anything
on this list requires an explicit decision to reverse, not a quiet feature add in a later phase.

## Scope boundaries requested directly

- **No unrestricted web search.** The chatbot does not perform open-ended web search for
  arbitrary queries. `GENERAL_KNOWLEDGE` is the only intent permitted any form of external
  lookup beyond the KB, it fires only after every other intent and the Track91 KB itself have
  been checked and missed, and even then its backing source is a decision for Phase 7/9 (likely
  constrained LLM knowledge, not a free-form search tool) — never a general-purpose search
  bolted onto every query.
- **No pricing answers without an approved source document.** `PRICING` is gated at
  generation time (Phase 7): it answers only from a chunk explicitly flagged as an approved
  pricing document (Phase 4 metadata). No approved chunk → fixed "contact support/sales"
  response. The LLM never estimates, infers, or extrapolates a price.
- **No live Track91 API or database integration in this phase.** Phase 1 produces taxonomy
  and planning documents only — no code, no mock or real API calls. The Fleet GPS API is
  mocked starting in later phases (per the roadmap's confirmed environment assumptions); real
  Track91 API/DB integration is out of scope for the entire roadmap as currently approved, not
  just this phase.

## Write/action scope

- **No mutating actions via chat in v1.** `CREATE_GEOFENCE`, `ASSIGN_DRIVER_TO_VEHICLE`,
  `ACKNOWLEDGE_ALERT`, `SCHEDULE_MAINTENANCE` are reserved intent slots (taxonomy section C)
  but their tools are not implemented. v1 is a **read-only** assistant: it answers questions
  about live status, history, reports, and documentation, and never changes fleet state.
  *Flagged assumption — confirm before Phase 9 builds the tool registry.*

## Data and integration scope

- **All data is mocked/synthetic for this build.** No real fleet records, no real KB
  documents, no real GPS device data — confirmed at Phase 1 kickoff. Synthetic data must be
  clearly marked as such in seed scripts and fixtures so it's never mistaken for production
  data later.
- **No AWS-specific code** until explicitly reached in Phase 13 — Docker Compose only until
  then, per the roadmap.
- **No proactive/push notifications.** The bot is reactive (answers when asked); it does not
  independently push alerts, digests, or reminders to users. A separate notification system,
  if it exists, is out of scope here.
- **No raw GPS breadcrumb replay.** Trip history is stored/served as summarized trips (start,
  end, stops, distance, duration), not an infinite-retention stream of raw location pings.
  *Flagged assumption — confirm retention granularity before Phase 3 schema is finalized.*

## Interface and access scope

- **English only** for v1 — no multi-language intent classification or generation.
- **No voice interface** — text chat only (API-driven; the actual UI surface is TBD in Phase
  11/13).
- **Single channel** — no SMS/WhatsApp/email integration assumed for v1.
  *Flagged assumption — confirm if any of these are required.*
- **No fine-grained in-company RBAC.** Tenant isolation is enforced by `company_id` at the
  repository layer (hard requirement); role-based restrictions *within* a company (e.g.
  dispatcher vs. fleet manager seeing different data) are not designed in this roadmap unless
  raised later. *Flagged assumption.*

## Engineering scope

- **No payment/billing transactions via chat** — the bot can discuss pricing (gated, see
  above) but never processes a purchase, upgrade, or payment.
- **No end-user document upload at chat time.** KB ingestion (Phase 5) is an offline/admin
  pipeline; end users cannot hand the bot a document to reason over mid-conversation in v1.
- **No custom model fine-tuning.** Embeddings and LLM are used off-the-shelf/self-hosted or
  via API, per the fixed tech stack — no training pipeline in this roadmap.
- **No production-grade observability stack.** Structured logging with correlation IDs
  (Phase 11+) is required; dashboards, alerting, and SLAs are out of scope for a <50-concurrent
  pilot unless requested.

## Items flagged for confirmation

The following are working assumptions used to keep Phase 1 moving — they are not blocking, but
should be confirmed before the phase that depends on them starts:

| Assumption | Depends-on phase |
|---|---|
| v1 is read-only (no write/action tools) | Phase 9 |
| India vehicle-plate format for `vehicle_ref` regex | Phase 6 |
| IST as default session timezone | Phase 6 |
| Trip history stored as summarized trips, not raw GPS breadcrumbs | Phase 3 |
| Single channel (no SMS/WhatsApp/email) | Phase 11/13 |
| No in-company RBAC beyond tenant isolation | Phase 3/11 |
