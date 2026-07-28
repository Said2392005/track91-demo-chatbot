# Entity Taxonomy — Phase 1

## Purpose

Entities are the slot-fillers the Phase 9 router needs to call a tool, and the values the
Phase 8 memory needs to track as "active entities" for coreference ("it", "that truck").
Every `_ref` entity below has two forms: the **raw span** extracted from text (what the user
typed) and a **canonical ID** it resolves to (what the tool call actually uses) — resolution
happens in Phase 6, against `MONGO_REPO` roster data, never guessed by the LLM.

| Entity | Type | Format / examples | Extraction method | Canonicalizes to | Notes |
|---|---|---|---|---|---|
| `vehicle_ref` | raw span | "MH12AB1234", "mh 04 ab 1234", "MH-04-AB-1234", "truck 45", "the Pune van", "it" | Normalize (below) → regex (plate format) + dictionary lookup (nickname/asset tag) + pronoun | `vehicle_id` | Plate regex assumed India format (Track91 is India-focused) — **flagged assumption, confirm before Phase 6**. |
| `vehicle_id` | canonical ID | Internal Mongo `_id` / fleet-API vehicle ID | Resolved, not extracted | — | Resolution requires a `company_id`-scoped roster lookup; ambiguous/no-match → `CLARIFICATION_NEEDED`. |
| `driver_ref` | raw span | "Ramesh", "the driver of MH12AB1234", "he/she" | NER (person name) + dictionary lookup + pronoun | `driver_id` | Name collisions within a company → `CLARIFICATION_NEEDED`. |
| `driver_id` | canonical ID | Internal Mongo `_id` | Resolved, not extracted | — | Same tenant-scoping rule as `vehicle_id`. |
| `date_expression` / `date_range` | temporal | "yesterday", "last week", "3 July to 10 July", "this month" | Rule-based relative-date parser + absolute date parser | ISO `(start_date, end_date)` | Anchored to session timezone (default IST — assumption, confirm) and "now" at request time, not message time. |
| `alert_type` | enum | speeding, harsh_braking, harsh_acceleration, idle, panic, geofence_entry, geofence_exit, low_fuel, device_offline, maintenance_due | Dictionary/enum match | — | Closed set, defined fully in Phase 3 schema; classifier maps synonyms ("SOS" → `panic`) to the enum. |
| `metric_type` | enum | speed, fuel, odometer, engine_temperature, battery_voltage | Dictionary/enum match | — | Used to narrow `GET_VEHICLE_HEALTH`. |
| `geofence_ref` | raw span | "the Pune warehouse zone", "Zone A" | NER + dictionary lookup | `geofence_id` | Resolved against `company_id`-scoped geofence collection. |
| `fleet_group_ref` | raw span | "Mumbai fleet", "delivery vans", "Group B" | Dictionary lookup | `fleet_group_id` | Optional grouping dimension on vehicles; not all tenants will have groups defined. |
| `report_type` | enum | trip_summary, fuel_report, driver_scorecard, maintenance_report | Dictionary/enum match | — | Narrows report-shaped historical intents when the user names a report explicitly. |
| `location_ref` | raw span (free text) | "our Pune warehouse", "MG Road, Bangalore" | NER (place/address) | Geocoded lat/lng | Only used by backlog `CREATE_GEOFENCE`; no resolution built until that intent leaves backlog. |
| `kb_topic` | raw span (free text) | "geofencing", "harsh braking", "add a driver", "AIS-140", "data retention" | Passed through to Phase 7 retrieval as the query text | — | Not canonicalized to an ID — it's the retrieval query itself, shared by `EXPLAIN_FEATURE`, `APP_FAQ`, `TROUBLESHOOTING_DEVICE`, `POLICY_QUESTION`, `PRICING`, `GENERAL_KNOWLEDGE`. |
| `plan_tier_ref` | raw span | "Pro plan", "Enterprise", "50-vehicle tier" | Dictionary lookup against known plan names (from KB) | — | Optional narrowing entity for `PRICING`; absence doesn't block the gate check, it just widens retrieval. |
| `pronoun_ref` | raw span | "it", "that one", "this vehicle", "them" | Coreference resolver (Phase 6/8) | Last active `vehicle_id`/`driver_id`/`geofence_id` in session memory | Resolution source is Phase 8's active-entity tracker; if session has no matching active entity → `CLARIFICATION_NEEDED`. |
| `company_id` | context, not extracted | Auth/session-derived tenant ID | Injected from auth context | — | **Never** parsed from user text. Every `MONGO_REPO`/`LIVE_API` call is scoped by this regardless of what entities were extracted — enforced at the repository layer per the roadmap's tenant-isolation rule. |

## `vehicle_ref` normalization rule

Registration numbers arrive messy — mixed case, inconsistent spacing/punctuation ("MH 04 AB
1234", "mh-04-ab-1234", "MH04AB1234"). Before any regex match or lookup, every candidate span
runs through a fixed normalization pipeline so all of these collapse to one canonical form:

1. Strip leading/trailing whitespace.
2. Uppercase all characters.
3. Remove all internal separators — spaces, hyphens, dots (`[\s\-\.]`).
4. Validate the result against the canonical plate regex: `^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$`.
5. If it matches, the normalized string *is* the canonical `plate_number` used for the roster
   lookup (`vehicle_id` resolution) — no further transformation.
6. If it doesn't match after normalization, it isn't a plate — fall through to the
   nickname/asset-tag dictionary lookup (still case-insensitive) rather than rejecting outright.

This means "MH12AB1234", "mh 04 ab 1234", and "MH-04-AB-1234" all normalize to the same
canonical key before lookup, and match/no-match is never sensitive to how the user spaced or
cased the plate. **Dependency on Phase 3**: the vehicle roster collection must store
`plate_number` in this same normalized form, so resolution is an exact-match lookup rather than
a fuzzy one — Phase 3's schema should apply this rule at write time (seed data and any future
ingestion), not just at query time.

## Notes for later phases

- **Phase 3** owns the authoritative enum values for `alert_type`, `metric_type`, and
  `report_type`, and the collections `vehicle_ref`/`driver_ref`/`geofence_ref`/`fleet_group_ref`
  resolve against.
- **Phase 6** owns extraction (regex/NER/dictionary) and canonicalization logic, plus the
  malformed/partial-input test cases (e.g. a plate typed with a space or lowercase).
- **Phase 8** owns the active-entity tracker that `pronoun_ref` resolves against, and defines
  how long an entity stays "active" in a session (e.g. does asking about a different vehicle
  replace the active vehicle, or stack).
- Two assumptions are flagged above (India plate format, IST default timezone) — confirm both
  before they're load-bearing in Phase 6.
