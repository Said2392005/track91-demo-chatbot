# Intent Taxonomy — Phase 1

## Purpose

Every intent below is a leaf in a **deterministic routing table** (built in Phase 9). The
semantic classifier (Phase 6) only picks a leaf from this fixed list — it never invents new
routing behavior. Each intent declares which subsystem answers it, which keeps the
"live data is never cached" rule (see roadmap) enforceable by construction: if
`target_subsystem = LIVE_API`, no repository or vector-store code path is allowed to serve it.

Columns:
- **Target subsystem** — `LIVE_API` (mock Fleet GPS API today, real API later, never
  persisted), `MONGO_REPO` (historical data via repository layer), `RAG` (ChromaDB +
  generation), `GENERAL_FALLBACK` (restricted, last-resort, see notes), or `NONE` (no data
  fetch — pure conversational).
- **MVP** — `Yes` (Phase 9-12 implement this), `Backlog` (taxonomy slot reserved, tool not
  built until explicitly requested — see non-goals doc), included so later phases don't have
  to re-derive scope.

## A. Live data intents (`LIVE_API`)

Never stored in Mongo/Chroma. Always fetched fresh per request.

| Intent | Description | Example utterances | Required entities | Optional entities | MVP |
|---|---|---|---|---|---|
| `GET_VEHICLE_LOCATION` | Current GPS position of a vehicle | "Where is MH12AB1234 right now?" · "Track truck 45" · "Current location of the Pune van" | `vehicle_ref` | — | Yes |
| `GET_VEHICLE_SPEED` | Current speed | "How fast is MH12AB1234 going?" · "What's its speed?" | `vehicle_ref` | — | Yes |
| `GET_VEHICLE_FUEL_LEVEL` | Current fuel level | "Fuel level on MH12AB1234?" · "How much fuel does it have left?" | `vehicle_ref` | — | Yes |
| `GET_VEHICLE_HEALTH` | Live engine/health telemetry (temp, battery, DTC codes) | "Any engine warnings on MH12AB1234?" · "Is the vehicle healthy?" | `vehicle_ref` | `metric_type` | Yes |
| `GET_VEHICLE_IGNITION_STATUS` | Ignition on/off, moving/idle/parked | "Is MH12AB1234 on or off?" · "Is it moving?" | `vehicle_ref` | — | Yes |
| `GET_FLEET_LIVE_STATUS` | Aggregate live snapshot across the fleet | "How many vehicles are moving right now?" · "Live status of my fleet" | — | `fleet_group_ref` | Yes |

## B. Historical data intents (`MONGO_REPO`)

Served via the repository layer, always scoped by `company_id`.

| Intent | Description | Example utterances | Required entities | Optional entities | MVP |
|---|---|---|---|---|---|
| `GET_TRIP_HISTORY` | List of past trips for a vehicle/driver | "Show MH12AB1234's trips yesterday" · "Trips for Ramesh last week" | `vehicle_ref` or `driver_ref`, `date_range` | — | Yes |
| `GET_TRIP_SUMMARY` | Aggregated distance/duration/stops over a period | "How many km did the Mumbai fleet cover last week?" | `date_range` | `vehicle_ref`, `fleet_group_ref` | Yes |
| `GET_ALERT_HISTORY` | Past alerts (speeding, geofence, panic, idle, etc.) | "Any speeding alerts for MH12AB1234 this month?" · "Panic alerts today" | `date_range` | `vehicle_ref`, `driver_ref`, `alert_type` | Yes |
| `GET_MAINTENANCE_HISTORY` | Past service records | "When was MH12AB1234 last serviced?" | `vehicle_ref` | `date_range` | Yes |
| `GET_MAINTENANCE_DUE` | Upcoming/overdue service | "Which vehicles are due for service?" | — | `vehicle_ref`, `fleet_group_ref` | Yes |
| `GET_DRIVER_BEHAVIOR_REPORT` | Driving score, harsh events, violations | "What's Ramesh's driving score this month?" | `driver_ref`, `date_range` | — | Yes |
| `GET_FUEL_CONSUMPTION_REPORT` | Fuel efficiency / consumption over time | "Fuel efficiency report for the Mumbai fleet" | `date_range` | `vehicle_ref`, `fleet_group_ref` | Yes |
| `GET_GEOFENCE_LIST` | Geofences configured for a vehicle/group | "What geofences apply to MH12AB1234?" | — | `vehicle_ref`, `fleet_group_ref` | Yes |
| `GET_VEHICLE_ROSTER` | Static vehicle metadata (make, model, plate, group) | "List all my vehicles" · "Show vehicles in the Pune group" | — | `fleet_group_ref` | Yes |
| `GET_DRIVER_ROSTER` | List of drivers and their assigned vehicles | "List all drivers" · "Who drives MH12AB1234?" | — | `vehicle_ref` | Yes |

## C. Action / write intents (`MONGO_REPO`, mutating)

Reserved taxonomy slots. **Backlog for v1** — see non-goals doc. Included now so Phase 9's
routing table has a defined (rejected) behavior instead of an undefined one if a user asks.

| Intent | Description | Example utterances | Required entities | MVP |
|---|---|---|---|---|
| `CREATE_GEOFENCE` | Define a new geofence | "Create a geofence around our Pune warehouse" | `location_ref`, `geofence_name` | Backlog |
| `ASSIGN_DRIVER_TO_VEHICLE` | Change driver-vehicle assignment | "Assign Ramesh to MH12AB1234" | `driver_ref`, `vehicle_ref` | Backlog |
| `ACKNOWLEDGE_ALERT` | Mark an alert as handled | "Acknowledge the speeding alert on MH12AB1234" | `vehicle_ref`, `alert_type` or `alert_id` | Backlog |
| `SCHEDULE_MAINTENANCE` | Book a service appointment | "Schedule a service for MH12AB1234 next week" | `vehicle_ref`, `date_expression` | Backlog |

## D. Knowledge-base intents (`RAG` / `GENERAL_FALLBACK`)

Answered via retrieval + cited generation over ingested documents (Phase 4-7).

| Intent | Description | Example utterances | Required entities | MVP |
|---|---|---|---|---|
| `EXPLAIN_FEATURE` | How a platform feature works | "How does geofencing work?" · "What does the driver score mean?" | `kb_topic` | Yes |
| `EXPLAIN_ALERT_TYPE` | Definition/cause of an alert type | "What counts as harsh braking?" · "Why did I get a low-fuel alert?" | `alert_type` or `kb_topic` | Yes |
| `APP_FAQ` | How-to questions about using the Track91 app itself | "How do I register a new GPS device?" · "How do I add a driver?" · "How do I generate a trip report?" | `kb_topic` | Yes |
| `TROUBLESHOOTING_DEVICE` | Device/connectivity problem diagnosis | "My GPS device shows offline, what do I do?" | `kb_topic` | Yes |
| `POLICY_QUESTION` | Non-monetary account/platform policy — data retention, privacy, terms of use | "How long is trip data retained?" · "What happens to my data if I cancel?" | `kb_topic` | Yes |
| `PRICING` | Plan cost, pricing tiers, discounts. **Gated** — see notes below. | "How much does the Pro plan cost?" · "Is there a discount for 50+ vehicles?" | `kb_topic` | `plan_tier_ref` | Yes |
| `GENERAL_KNOWLEDGE` | Lowest-priority fallback: general domain knowledge not specific to Track91 and not covered by any KB doc or other intent. **Excluded** from account-specific and money-specific answers — see notes below. | "What does AIS-140 mean?" · "What's the difference between GPS and GLONASS?" | `kb_topic` | — | Yes |

### Gating rules (enforced in later phases, recorded here so they aren't lost)

- **Routing priority.** The classifier/router only reaches `GENERAL_KNOWLEDGE` after intents
  A-C, and every other D intent, have been checked and missed. It is the fallback of last
  resort, not a peer of `EXPLAIN_FEATURE`/`APP_FAQ`/etc. Its `target_subsystem` is
  `GENERAL_FALLBACK`, not `RAG`, to make this ordering visible in the routing table itself.
- **`PRICING` gate.** The classifier still routes any pricing-shaped question to `PRICING` —
  the *generation* step (Phase 7) is what enforces the gate: it checks whether the retrieved
  context includes a chunk from a source explicitly flagged as an approved pricing document
  (a metadata field defined in Phase 4). If no approved pricing chunk is retrieved, the answer
  is a fixed "contact support/sales" response — the LLM is never allowed to state, estimate,
  or infer a price from general knowledge or partial context.
- **`GENERAL_KNOWLEDGE` exclusions.** This intent must never resolve to `MONGO_REPO` or
  `LIVE_API` data, and must never be used to answer a `PRICING`- or `POLICY_QUESTION`-shaped
  query even when the KB has no matching document for it — an unanswered money/policy question
  falls back to "I don't have that information, please contact support," never to general
  trivia. Its backing source (LLM parametric knowledge vs. a scoped web-search tool) is decided
  in Phase 7/9; per the non-goals doc, it is never unrestricted web search over arbitrary
  queries.

## E. Conversational / meta intents (`NONE`)

No data fetch. Handled directly by the dialogue layer.

| Intent | Description | Example utterances | MVP |
|---|---|---|---|
| `GREETING` | Opening a conversation | "Hi" · "Hello" · "Good morning" | Yes |
| `GOODBYE` | Ending a conversation | "Thanks, bye" · "That's all" | Yes |
| `CHITCHAT` | Small talk unrelated to fleet data | "How are you?" · "What can you do?" | Yes |
| `CLARIFICATION_NEEDED` | Ambiguous/missing entity in an otherwise valid intent | "What's its speed?" with no prior vehicle in context | Yes |
| `AFFIRM_DENY` | Yes/no follow-up to a bot-asked clarifying question | "Yes, that one" · "No, the other truck" | Yes |
| `OUT_OF_SCOPE` | Request outside fleet-management domain entirely | "Write me a poem" · "What's the weather in Delhi?" | Yes |

## Notes for Phase 6/9

- `CLARIFICATION_NEEDED` and `AFFIRM_DENY` are not classified from the raw utterance in
  isolation — they depend on dialogue state (was a clarifying question just asked?). Phase 8's
  session memory is a hard dependency for these two.
- Every intent in sections A-D that takes `vehicle_ref`/`driver_ref` must go through the
  coreference/entity-resolution step (Phase 6) before reaching the Phase 9 router, so "it"/"that
  truck" resolve to a canonical `vehicle_id` the same way an explicit registration number does.
- `PRICING` and `GENERAL_KNOWLEDGE` gating logic (above) must be implemented as fixed
  conditional checks in the Phase 7 generation node, not left to LLM discretion — consistent
  with the "LLM only phrases the final answer" rule.
