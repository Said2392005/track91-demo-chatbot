# Trigger-phrase coverage — history and current state

## What this is

`RuleBasedIntentClassifier` (`app/nlu/intent_classifier.py`) scores an utterance against
`app/nlu/trigger_patterns.py`'s per-intent `TRIGGER_PHRASES` (literal substrings),
`TRIGGER_REGEXES`, and `TRIGGER_COOCCURRENCE` (verb-list × subject-list) tables.
`TRIGGER_PHRASES` alone only ever covers phrasings someone thought to type in ahead of time —
found live, repeatedly, that realistic rewordings (and, most recently, bare keywords/nouns with
no verb at all — "drivers", "vehicles", "alerts") routinely miss every listed phrase and fall
through to `OUT_OF_SCOPE`/`GENERAL_KNOWLEDGE`.

This was fixed in two passes. The first (below) covered 4 high-traffic intents and documented
the rest as a known gap. The second, all-intent pass closed nearly all of that gap — this doc now
reflects that final state, not just the first pass.

## Pass 2: all-intent systematic probe (current state)

An 88-probe check ran realistic paraphrases (different verbs, noun-first phrasing, dropped
articles, "how many X"/"list of X" shapes) **plus a bare-keyword/noun-only category** (no verb
at all — the specific pattern that kept recurring: "drivers" alone, "vehicles" alone, "alerts"
alone) against all 32 text-classifiable intents (every intent in `app/core/taxonomy.py` except
`CLARIFICATION_NEEDED`/`AFFIRM_DENY`, which are session-state driven, not text-triggered).

**Before: 28/88 (31.8%).** **After: 86/88 (97.7%).**

Per-intent, before → after (only intents with any failures shown; everything else was already
at 100% — `PRICING`, `EXPLAIN_ALERT_TYPE`, `GENERAL_KNOWLEDGE`, `OUT_OF_SCOPE`):

| Intent | Before | After |
|---|---|---|
| `GET_VEHICLE_LOCATION` | 0/2 | 2/2 |
| `GET_VEHICLE_SPEED` | 0/2 | 2/2 |
| `GET_VEHICLE_FUEL_LEVEL` | 1/2 | 2/2 |
| `GET_VEHICLE_HEALTH` | 0/4 | 4/4 |
| `GET_VEHICLE_IGNITION_STATUS` | 1/3 | 3/3 |
| `GET_FLEET_LIVE_STATUS` | 0/3 | 3/3 |
| `GET_TRIP_HISTORY` | 1/4 | 4/4 |
| `GET_TRIP_SUMMARY` | 1/3 | 3/3 |
| `GET_ALERT_HISTORY` | 0/3 | 3/3 |
| `GET_MAINTENANCE_HISTORY` | 1/3 | 3/3 |
| `GET_MAINTENANCE_DUE` | 1/3 | 3/3 |
| `GET_DRIVER_BEHAVIOR_REPORT` | 1/3 | 3/3 |
| `GET_FUEL_CONSUMPTION_REPORT` | 1/3 | 3/3 |
| `GET_GEOFENCE_LIST` | 1/3 | 3/3 |
| `GET_VEHICLE_ROSTER` | 1/4 | 4/4 |
| `GET_DRIVER_ROSTER` | 0/3 | 3/3 |
| `CREATE_GEOFENCE` | 1/3 | 3/3 |
| `ASSIGN_DRIVER_TO_VEHICLE` | 1/3 | 1/3 |
| `ACKNOWLEDGE_ALERT` | 1/3 | 3/3 |
| `SCHEDULE_MAINTENANCE` | 0/3 | 3/3 |
| `EXPLAIN_FEATURE` | 1/2 | 2/2 |
| `APP_FAQ` | 0/3 | 3/3 |
| `TROUBLESHOOTING_DEVICE` | 1/3 | 3/3 |
| `POLICY_QUESTION` | 2/3 | 3/3 |
| `GREETING` | 1/2 | 2/2 |
| `GOODBYE` | 1/2 | 2/2 |
| `CHITCHAT` | 0/2 | 2/2 |
| `ABOUT_TRACK91` | 0/2 | 2/2 |

The fix was the same recipe used in pass 1, applied intent by intent, each re-verified against
both the probe suite and the full existing regression suite (`test_intent_classifier.py`,
`test_second_intent_eval.py`, `test_agent_graph_integration.py`) before moving to the next —
not a blind batch edit:
1. A `TRIGGER_COOCCURRENCE` entry (verb-phrases × subject-nouns) for the realistic
   question/command shapes.
2. `TRIGGER_REGEXES` for the bare-`<plate>`-plus-topic-noun shape (no verb at all) where the
   intent takes a `vehicle_ref`.
3. An explicit bare-keyword `TRIGGER_PHRASES` entry where a single word has exactly one
   sensible meaning in this taxonomy (see the ambiguous-keywords section below for where this
   was deliberately *not* done).

### Real regressions found and fixed along the way

Four of the new `TRIGGER_COOCCURRENCE` entries, as first written, caused **other**, previously-passing
cases to misclassify — each caught by re-running the full regression suite after adding the
table, not by inspection, and each fixed by removing an over-generic word rather than reverting
the fix:
- `GET_VEHICLE_HEALTH`'s bare `"is"` verb stole "How quick is it moving right now?" from
  `GET_VEHICLE_SPEED`. Replaced with specific phrases ("is it healthy", "is the vehicle
  healthy").
- `GET_VEHICLE_IGNITION_STATUS`'s bare `"running"`, present in *both* its verb and subject
  lists, self-paired to wrongly register a second, phantom intent on "Is MH12AB1234's engine ok
  and running smoothly?" (a health question) — caught by the dual-intent false-positive eval
  (`app/eval/second_intent_eval.py`). Dropped entirely; already covered by the existing literal
  "is it running" phrase.
- `GET_VEHICLE_ROSTER`'s `"how many"` verb, paired with bare `"vehicles"`, stole "How many
  vehicles are active now?" from `GET_FLEET_LIVE_STATUS`. Dropped; not needed by any real case.
- `GET_DRIVER_BEHAVIOR_REPORT`'s bare `"score"`, present in both lists, double-counted (phrase
  match + cooccurrence self-pairing) to a score that tied, and — checked first by category
  order — beat, `EXPLAIN_FEATURE`'s genuine match on "What does the driver score mean?". Fixed
  by keeping `"score"` as a verb only, paired with `"this month"`/`"driving"` as the subject.
- `TROUBLESHOOTING_DEVICE`'s bare `"offline"` verb, paired with `"device"`, outscored
  `EXPLAIN_ALERT_TYPE`'s genuine match on "What is a device offline alert?" (asking what the
  alert means, not reporting a problem). Replaced with `"going offline"`.

The general lesson, not just these five instances: a single generic word in a
`TRIGGER_COOCCURRENCE` list — especially one appearing in both the verb and subject side of the
*same* table — is a real collision risk, not a theoretical one. Every new cooccurrence entry in
this pass was re-checked against the full regression suite specifically because of this.

### Ambiguous bare keywords — decided and documented, not silently guessed

A few single words genuinely name more than one real intent in this taxonomy. Adding a trigger
for one of them would mean silently guessing wrong some real fraction of the time. Decided,
case by case, not to add a bare trigger for any of these — pinned as an explicit classifier
test (`test_ambiguous_bare_keywords_are_not_silently_guessed` in `test_intent_classifier.py`)
asserting they still correctly fall through to `GENERAL_KNOWLEDGE`/`OUT_OF_SCOPE` rather than
resolve to a guess:

| Bare word | Genuinely competing intents | Decision |
|---|---|---|
| `trips` | `GET_TRIP_HISTORY` (list) vs `GET_TRIP_SUMMARY` (aggregate) | Not resolved |
| `maintenance` / `service` | `GET_MAINTENANCE_HISTORY` (past) vs `GET_MAINTENANCE_DUE` (upcoming) vs `SCHEDULE_MAINTENANCE` (action) | Not resolved |
| `fuel` | `GET_VEHICLE_FUEL_LEVEL` (one vehicle, now) vs `GET_FUEL_CONSUMPTION_REPORT` (fleet, aggregate) | Not resolved (the exact collision risk flagged in pass 1, below) |
| `status` | `GET_VEHICLE_IGNITION_STATUS` vs `GET_FLEET_LIVE_STATUS` vs a general condition reading | Not resolved |
| `history` | `GET_TRIP_HISTORY` vs `GET_ALERT_HISTORY` vs `GET_MAINTENANCE_HISTORY` (three intents literally named `*_HISTORY`) | Not resolved |
| `alert` (singular) | Too tied up with `ACKNOWLEDGE_ALERT`/`EXPLAIN_ALERT_TYPE`'s own vocabulary | Not resolved |

Contrast with the words that **were** given a bare trigger, and why they're different — each one
was checked against the full 34-intent taxonomy for a second plausible reading, not just assumed
safe:
- `drivers` / `which drivers` → `GET_DRIVER_ROSTER`. `GET_DRIVER_BEHAVIOR_REPORT` always needs a
  specific driver name plus a score/behavior word, so a bare plural with neither has one
  sensible reading.
- `vehicles` / `my vehicles` → `GET_VEHICLE_ROSTER`. The one genuinely-debatable case in this
  pass (a bare plural could in the abstract be a cut-off question) — decided in favor of adding
  it: every vehicle-specific `LIVE_API` intent needs a *specific* vehicle_ref, which a bare
  plural doesn't suggest, so there's no real second candidate among this taxonomy's actual
  intents.
- `alerts` (plural, unlike singular `alert` above) → `GET_ALERT_HISTORY`. Both
  `ACKNOWLEDGE_ALERT` and `EXPLAIN_ALERT_TYPE` always need an action verb or a question-shaped
  "what does"/"why did" verb respectively, so a bare plural noun with neither is unambiguous.
- `geofences` (plural) → `GET_GEOFENCE_LIST`, vs `geofencing` (gerund) → `EXPLAIN_FEATURE`. A
  real, defensible linguistic distinction: the plural noun names the *configured zones*, the
  gerund names the *feature/concept* — not a coin flip.
- `location`, `speed`, `fleet status`, `faq`, `policy`, `track91` → each checked individually;
  no other intent's vocabulary uses any of them.

## Left as-is: `ASSIGN_DRIVER_TO_VEHICLE`'s remaining 2 paraphrases

"Put Ramesh on MH12AB1234" and "Ramesh should drive MH12AB1234 now" still fall through. Not
fixed, deliberately: catching these would need generic verbs ("put", "should drive") that carry
real false-positive risk across the rest of the domain, for an intent that's backlog/unimplemented
(`mvp=False` in `app/core/taxonomy.py` — the router refuses it via `BACKLOG_UNSUPPORTED`
regardless of how well it classifies). The cost/benefit didn't clear the bar the other 27 fixes
did. Existing coverage (`assign`-based phrasings, the `\bassign (\w+\s?){1,3}to\b` regex) is
unchanged.

## Pass 1: the original 4-intent fix (history)

A 41-probe check ran the same style of realistic-paraphrase probes against all 16
`LIVE_API`/`MONGO_REPO` intents that existed at the time — **40 of 41 failed** before any fix.
`GET_VEHICLE_LOCATION`, `GET_VEHICLE_SPEED`, `GET_VEHICLE_FUEL_LEVEL`, `GET_DRIVER_ROSTER` were
moved to `TRIGGER_COOCCURRENCE` (verb-list × subject-list), plus a bare-plate `TRIGGER_REGEXES`
addition for the plate-directly-followed-by-topic-noun shape cooccurrence structurally can't
reach ("MH12AB1234 speed"). Re-running the same probes against just these four: 13/13 (100%),
up from 0/13. The other 12 intents' gap, and the `GET_FUEL_CONSUMPTION_REPORT`/
`GET_VEHICLE_FUEL_LEVEL` cross-intent confusion risk flagged at the time, were tracked here
rather than fixed — both addressed in pass 2 above.

## If more gaps turn up later

Same recipe as both passes: add a `TRIGGER_COOCCURRENCE` entry, re-run the **full** regression
suite (not just the new probe) before considering it done — pass 2 found 5 real regressions this
way that inspection alone would have missed — and if a bare keyword is involved, check it
against the full 34-intent taxonomy for a second plausible reading before adding it as a
trigger. If it has one, document the ambiguity here and in a pinned test, the same way the six
words above were — don't guess silently.
