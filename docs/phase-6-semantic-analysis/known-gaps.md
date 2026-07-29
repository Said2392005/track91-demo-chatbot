# Known gap: narrow trigger-phrase coverage on most LIVE_API/MONGO_REPO intents

## What this is

`RuleBasedIntentClassifier` (`app/nlu/intent_classifier.py`) scores an utterance against
`app/nlu/trigger_patterns.py`'s per-intent `TRIGGER_PHRASES` (literal substrings),
`TRIGGER_REGEXES`, and `TRIGGER_COOCCURRENCE` (verb-list × subject-list) tables. `TRIGGER_PHRASES`
alone only ever covers phrasings someone thought to type in ahead of time — it was found (live,
twice: `GET_VEHICLE_SPEED`'s "what is my vehicle speed", `GET_DRIVER_ROSTER`'s "how many
drivers") that realistic rewordings routinely miss every listed phrase and fall through to
`OUT_OF_SCOPE`/`GENERAL_KNOWLEDGE`.

## The systematic check that quantified it

A 41-probe check ran realistic paraphrases (different verbs, noun-first phrasing, dropped
articles, "how many X"/"list of X"/bare-plate-plus-topic-noun shapes) against all 16
`LIVE_API`/`MONGO_REPO` intents — **40 of 41 failed** before any fix. This was not a couple of
stray gaps; it's structural to phrase-list-only matching.

## Fixed (4 intents, highest-traffic first)

`GET_VEHICLE_LOCATION`, `GET_VEHICLE_SPEED`, `GET_VEHICLE_FUEL_LEVEL`, `GET_DRIVER_ROSTER` were
moved to the `TRIGGER_COOCCURRENCE` pattern already proven for `EXPLAIN_FEATURE`/
`EXPLAIN_ALERT_TYPE` (verb-list × subject-list, so N+M entries cover N×M phrasings), plus a
small bare-plate `TRIGGER_REGEXES` addition for the one shape cooccurrence structurally can't
reach: a plate number directly followed by a topic noun with no verb at all ("MH12AB1234
speed", "MH12AB1234's location") — a noun phrase, not a question, so there's no verb-list entry
for it to match. Re-running the same probes against just these four: **13/13 pass (100%)**, up
from 0/13.

## Not yet fixed — tracked here, not silently

The remaining 12 `LIVE_API`/`MONGO_REPO` intents still use `TRIGGER_PHRASES` only, with the same
shape of gap. Sample size is small (2-3 probes per intent, not exhaustive) — treat the
percentages as indicative of a real, structural problem, not a precise measurement.

| Intent | Failure rate (sample) | Example phrasing that fails |
|---|---|---|
| `GET_VEHICLE_HEALTH` | 3/3 (100%) | "is MH12AB1234 healthy", "any problems with MH12AB1234", "MH12AB1234 diagnostics" |
| `GET_VEHICLE_IGNITION_STATUS` | 2/2 (100%) | "is MH12AB1234 turned on", "MH12AB1234 ignition" |
| `GET_FLEET_LIVE_STATUS` | 3/3 (100%) | "what's my fleet status", "number of vehicles moving", "fleet overview" |
| `GET_TRIP_HISTORY` | 3/3 (100%) | "trips MH12AB1234 made", "where has MH12AB1234 been today", "journey history for MH12AB1234" |
| `GET_TRIP_SUMMARY` | 2/2 (100%) | "how far did MH12AB1234 travel this week", "total km this week" |
| `GET_ALERT_HISTORY` | 2/2 (100%) | "what alerts happened today", "alerts for MH12AB1234 today" |
| `GET_MAINTENANCE_HISTORY` | 2/2 (100%) | "service records for MH12AB1234", "maintenance log for MH12AB1234" |
| `GET_MAINTENANCE_DUE` | 2/2 (100%) | "what needs servicing", "vehicles that need maintenance" |
| `GET_DRIVER_BEHAVIOR_REPORT` | 2/2 (100%) | "how is Ramesh Kumar driving this month", "Ramesh Kumar's score this month" |
| `GET_FUEL_CONSUMPTION_REPORT` | 2/2 (100%) | "fuel usage report" (`OUT_OF_SCOPE`); "how much fuel are we using this month" (misclassifies as `GET_VEHICLE_FUEL_LEVEL` — a pre-existing cross-intent confusion, not introduced by this pass's `GET_VEHICLE_FUEL_LEVEL` fix; it misclassified the same way before) |
| `GET_GEOFENCE_LIST` | 1/2 (50%) | "what zones apply to MH12AB1234" ("geofences for MH12AB1234" already passes) |
| `GET_VEHICLE_ROSTER` | 3/3 (100%) | "my vehicles", "what vehicles do I have", "vehicles list" |

## If/when this gets picked up

Follow the same recipe used for the 4 fixed intents:
1. Add a `TRIGGER_COOCCURRENCE` entry (verb-phrases × subject-nouns) covering the realistic
   question/command shapes.
2. Add 1-2 `TRIGGER_REGEXES` for the bare-"`<plate>` + topic-noun" shape if the intent takes a
   `vehicle_ref` (reuse `_PLATE_SPAN` already defined in `trigger_patterns.py`).
3. Re-run the probes for that intent specifically and confirm before moving to the next one —
   don't batch-fix all 12 blind; `GET_FUEL_CONSUMPTION_REPORT`/`GET_VEHICLE_FUEL_LEVEL` above is
   a concrete example of two intents sharing enough vocabulary ("fuel") that a cooccurrence table
   for one can shift scoring for the other — worth an explicit disambiguating check when it's
   `GET_FUEL_CONSUMPTION_REPORT`'s turn.
