# ADR 004: Tenant Scoping Enforcement at the Repository Layer

## Status

Accepted

## Context

Cross-tenant data leakage (one company seeing another company's vehicles/trips/alerts) is a
correctness and trust failure, not a cosmetic bug. Enforcing `company_id` scoping per-endpoint
is fragile — it's easy to add a new route or a new query path later and forget the filter.

## Decision

`company_id` is a required, non-optional parameter on every repository method that touches
tenant-scoped data (see [[001-repository-pattern-for-mongo]]). Repositories construct the Mongo
filter internally and always AND it with `{company_id: ...}` — callers pass data in, they never
construct the raw filter. `company_id` is sourced exclusively from the authenticated
session/auth context resolved by middleware (Phase 11); it is never parsed from user message
text, never inferred by the LLM, and never accepted as a client-supplied request field.
Compound indexes (Phase 3) lead with `company_id` so scoping is also the performant access
path, not just a correctness constraint.

## Consequences

- A missing `company_id` is a code-level error (missing required argument) caught at
  development/test time, not a silent unscoped query at runtime.
- Every repository's test suite (Phase 3) must include a cross-tenant isolation case: seed two
  companies' data, query as one, assert the other's data never appears.
- This slightly limits query flexibility (no "query across all companies" convenience method) —
  accepted deliberately; an admin/cross-tenant use case, if it ever arises, would be a distinct,
  explicitly-named repository method, not a relaxation of this rule.
