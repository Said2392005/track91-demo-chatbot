# APIs Needed From Manager

The bot currently answers the questions below using either **fake, mocked data**
(`MockFleetGPSClient`, for live telemetry) or **no data at all**, because the underlying database
tables were deleted from the codebase (for vehicle/driver rosters). To go live, real data feeds
are needed for each of the following before the real integration can be wired up.

## Current state

None of the live-telemetry items (#1–#6) exist as real integrations yet. Per the project's own
planning docs (`docs/phase-1-planning/non-goals.md`), real Track91/Fleet GPS API integration was
marked explicitly out of scope for the whole roadmap as approved — everything below is currently
served by `MockFleetGPSClient`, random data seeded per vehicle, never real telemetry.

The roster items (#7–#8) are in worse shape: as of this doc, `vehicle_repository.py` and
`driver_repository.py` were **deleted from the codebase**, and the underlying `vehicles` /
`drivers` MongoDB collections were **removed from the schema entirely**
(`backend/app/db/schema_definitions.py` now only defines `organizations`/`users`/`products` — a
generic org/product model, not fleet-specific). The code that still calls these deleted repos
(`backend/app/tools/history_tools.py`) is currently broken (import errors) as a result. This is
worth a direct question to the manager, not just a data-feed ask — see the flag below.

## Live telemetry (mocked today — see #1–#6)

## 1. Vehicle Location API
- **Answers:** "Where is my vehicle right now?"
- **Data needed:** current lat, lng, timestamp — for one vehicle
- **Feeds intent:** `GET_VEHICLE_LOCATION`

## 2. Vehicle Speed API
- **Answers:** "How fast is my vehicle going?"
- **Data needed:** current speed (km/h), timestamp — for one vehicle
- **Feeds intent:** `GET_VEHICLE_SPEED`

## 3. Vehicle Fuel Level API
- **Answers:** "How much fuel does my vehicle have left?"
- **Data needed:** current fuel level (%), timestamp — for one vehicle
- **Feeds intent:** `GET_VEHICLE_FUEL_LEVEL`

## 4. Vehicle Health / Diagnostics API
- **Answers:** "Any engine warnings? Is my vehicle healthy?"
- **Data needed:** engine temperature, battery voltage, active warning/DTC codes, timestamp — for one vehicle
- **Feeds intent:** `GET_VEHICLE_HEALTH`

## 5. Vehicle Ignition / Movement Status API
- **Answers:** "Is my vehicle on or off? Is it moving?"
- **Data needed:** ignition state (on/off), moving flag, timestamp — for one vehicle
- **Feeds intent:** `GET_VEHICLE_IGNITION_STATUS`

## 6. Fleet Live Status API
- **Answers:** "How many vehicles are moving right now?"
- **Data needed:** total vehicle count, moving count, idle count, timestamp — for a company (optionally one fleet group)
- **Feeds intent:** `GET_FLEET_LIVE_STATUS`

## Rosters (no backend at all today — see #7–#8)

## 7. Vehicle Roster API
- **Answers:** "List all my vehicles" / "Show vehicles in the Pune group" / "Who drives MH12AB1234?" (vehicle side)
- **Data needed:** list of vehicles for a company, each with: plate number, nickname, make, model, year, vehicle type, fleet group, assigned driver, device ID, status — optionally filterable by fleet group
- **Feeds intent:** `GET_VEHICLE_ROSTER` (also backs vehicle-side lookups for `GET_DRIVER_ROSTER`)

## 8. Driver / User Roster API
- **Answers:** "List all drivers" / "Who drives MH12AB1234?" (driver side)
- **Data needed:** list of drivers/users for a company, each with: name, phone, license number, status, and which vehicle (if any) they're assigned to
- **Feeds intent:** `GET_DRIVER_ROSTER`

## Questions to bring to the manager

- Which vendor/provider is the real live-telemetry data (#1–#6) coming from, and is there API documentation to share?
- Can #1–#5 be served by one combined "vehicle snapshot" endpoint instead of five separate calls? (Common for telematics providers — would simplify the integration.)
- Auth model for the real API (API key, OAuth, per-company credentials)?
- Expected update frequency / staleness tolerance for each feed?
- **For #7–#8:** is vehicle/driver roster data meant to come from a real fleet-management system as a source-of-truth API (this bot would then sync/cache it), or is it meant to be entered directly into this bot's own database? The schema was recently reshaped away from a fleet-specific model (`vehicles`/`drivers`/`trips`) toward a generic `organizations`/`users`/`products` model — worth confirming whether this product is still meant to be fleet-specific before rebuilding the roster APIs.

---
*#1–#6 derived from `backend/app/tools/fleet_gps_client.py` and `live_data_tools.py` (the current
mock) — those fields are exactly what those files already read and expect. #7–#8 derived from the
now-deleted `vehicle_repository.py` / `driver_repository.py` (via `git show HEAD:...`) and the
prior `vehicles`/`drivers` schema definitions, since no current code path serves them.*
