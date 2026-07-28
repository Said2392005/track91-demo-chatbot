# ADR 001: Repository Pattern for MongoDB Access

## Status

Accepted

## Context

Multiple layers need history data — tool handlers (Phase 9), the session/checkpointer (Phase
8), and potentially admin/reporting code later. If each of these made raw `motor` calls
independently, tenant scoping (`company_id`) and query shape would need to be re-verified at
every call site, and testing would require a real or heavily mocked Mongo instance everywhere.

## Decision

All MongoDB access goes through a repository class, one per collection (`VehicleRepository`,
`DriverRepository`, `TripRepository`, `AlertRepository`, `MaintenanceRepository`,
`GeofenceRepository`, plus a `SessionRepository` for Phase 8 checkpoints). Repository modules
are the *only* code in the project permitted to `import motor`. Every method that reads or
writes tenant data takes `company_id` as a required positional argument — no default value, no
`Optional[str] = None`.

## Consequences

- Services, agent nodes, and routers depend on repository interfaces, not on Mongo — they're
  unit-testable with in-memory fakes.
- Adding a new collection means adding a new repository class; there is no second way to reach
  Mongo.
- Slight boilerplate (a repository class per collection) is accepted in exchange for the
  structural guarantee that tenant scoping can't be forgotten at a call site — see [[004-tenant-scoping-enforcement]].
- Schema validation and index definitions (Phase 3) live alongside their repository, keeping
  the "how this collection is queried" and "how it's shaped/indexed" knowledge co-located.
