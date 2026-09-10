"""
Trigger phrase/regex tables for RuleBasedIntentClassifier — one entry per intent in
app/core/taxonomy.py (except CLARIFICATION_NEEDED and AFFIRM_DENY, which are dialogue-state
driven rather than text-triggered, and GENERAL_KNOWLEDGE/OUT_OF_SCOPE, which are fallback
outcomes rather than positively triggered).

Scoring: a matched phrase scores by its word count (longer/more specific phrases outweigh short
generic ones); a matched regex scores a flat 3. Ties break by category priority order — the
order intents are declared in app/core/taxonomy.py (A live -> B history -> C backlog actions ->
D knowledge base -> E meta), matching the Phase 2 architecture's stated routing priority.
"""

import re

TRIGGER_PHRASES: dict[str, list[str]] = {
    # A. Live data
    "GET_VEHICLE_LOCATION": [
        "where is",
        "where's",
        "current location",
        "location of",
        "track my vehicle",
        "find my vehicle",
        "where can i find",
        # "vehicle location(s)" as a bare noun phrase (no verb, no plate) scored 0 — found
        # while building the dual-intent detector's eval set ("list drivers and vehicle
        # location(s)", the exact motivating example) — same class of gap as "vehicle speed"
        # earlier. Both singular and plural needed: \b-bounded matching means "vehicle
        # location" does not match inside "vehicle locations" (trailing "s" blocks the
        # word-boundary right after "location").
        "vehicle location",
        "vehicle locations",
        # Bare "location" alone — added via the all-intent systematic probe (see
        # docs/phase-6-semantic-analysis/known-gaps.md). Unambiguous: no other intent's
        # vocabulary uses "location" at all.
        "location",
        "whereabouts",
    ],
    "GET_VEHICLE_SPEED": [
        "how fast",
        "current speed",
        "its speed",
        "speed right now",
        "going at what speed",
        "what speed is",
        # Added after live testing surfaced "what is my vehicle speed" / "what is the speed of
        # my vehicle" falling through to GENERAL_KNOWLEDGE — neither matched any existing
        # phrase. \b-bounded matching (app/nlu/intent_classifier.py's _phrase_regex) means bare
        # "speed" is safe here: it won't match inside "speeding" (ACKNOWLEDGE_ALERT/
        # EXPLAIN_ALERT_TYPE's domain).
        "vehicle speed",
        "speed of",
        # Bare "speed" alone — added via the all-intent systematic probe. Unambiguous: \b-bounded
        # matching means it never matches inside "speeding" (ACKNOWLEDGE_ALERT/
        # EXPLAIN_ALERT_TYPE's domain), and no other intent's vocabulary uses bare "speed".
        "speed",
    ],
    "GET_VEHICLE_FUEL_LEVEL": [
        "fuel level",
        "how much fuel",
        "fuel left",
        "gas level",
        "petrol level",
        "fuel remaining",
    ],
    "GET_VEHICLE_HEALTH": [
        "engine warning",
        "engine warnings",
        "engine ok",
        "any issues with",
        "diagnostic",
        "check engine",
        "vehicle healthy",
        "health status",
        # Added via the all-intent systematic probe — see the new TRIGGER_COOCCURRENCE entry
        # below for the verb-phrase shapes ("is it healthy", "any problems with X").
        "engine health",
        "diagnostics",
    ],
    "GET_VEHICLE_IGNITION_STATUS": [
        "is it on or off",
        "ignition status",
        "is the ignition",
        "engine on or off",
        "is it running",
        "is it moving or parked",
        "on or off right now",
    ],
    "GET_FLEET_LIVE_STATUS": [
        "how many vehicles are moving",
        "live status of my fleet",
        "fleet status right now",
        "vehicles active now",
        "vehicles are active",
        "how many are idle right now",
        "current fleet status",
        # Bare "fleet status" — added via the all-intent systematic probe. Unambiguous: no other
        # intent's vocabulary combines "fleet"+"status".
        "fleet status",
    ],
    # B. Historical data
    "GET_TRIP_HISTORY": [
        "trip history",
        "show trips",
        "list of trips",
        "trips yesterday",
        "trips last week",
        "journeys made",
        "journeys did",
        "show me trips",
    ],
    "GET_TRIP_SUMMARY": [
        "how many km",
        "total distance",
        "distance covered",
        "km covered",
        "trip summary",
        "kilometers driven",
    ],
    "GET_ALERT_HISTORY": [
        "any alerts",
        "alert history",
        "list of alerts",
        "alerts this month",
        "alerts today",
        "past alerts",
        # Bare plural "alerts" alone — added via the all-intent systematic probe. Unambiguous
        # *as a plural*: ACKNOWLEDGE_ALERT always needs an action verb (acknowledge/dismiss/
        # clear/mark/resolve/close) and EXPLAIN_ALERT_TYPE always needs a question verb (what
        # does/why did), so neither collides with a bare noun. Bare *singular* "alert" is
        # deliberately NOT added here — see known-gaps.md's ambiguous-bare-keywords section.
        "alerts",
    ],
    "GET_MAINTENANCE_HISTORY": [
        "last serviced",
        "service history",
        "when was it serviced",
        "maintenance history",
        "last service",
        "when was the last service",
    ],
    "GET_MAINTENANCE_DUE": [
        "due for service",
        "service due",
        "which vehicles need service",
        "maintenance due",
        "due for maintenance",
        "upcoming service",
        "overdue for maintenance",
    ],
    "GET_DRIVER_BEHAVIOR_REPORT": [
        "driving score",
        "driver score",
        "behavior report",
        "driving behavior",
        "harsh events",
        "driver scorecard",
    ],
    "GET_FUEL_CONSUMPTION_REPORT": [
        "fuel report",
        "fuel efficiency",
        "fuel consumption",
        "mileage report",
        "fuel efficiency report",
    ],
    "GET_GEOFENCE_LIST": [
        "geofences apply",
        "which geofences",
        "list geofences",
        "geofences for",
        "geofence list",
        "what geofences",
        # Bare plural "geofences" alone — added via the all-intent systematic probe.
        # Unambiguous: \b-bounded matching means it doesn't match inside CREATE_GEOFENCE's
        # singular "geofence" phrases (the trailing "s" blocks the boundary), and
        # EXPLAIN_FEATURE's own "geofencing"/"geofence" cooccurrence subjects always require a
        # question-shaped verb alongside them, which a bare noun doesn't have.
        "geofences",
    ],
    "GET_VEHICLE_ROSTER": [
        "list all vehicles",
        "all my vehicles",
        "vehicle list",
        "show vehicles",
        "fleet roster",
        "show me my vehicles",
        # Bare "vehicles"/"my vehicles" — added via the all-intent systematic probe. This is
        # the one genuinely-debatable case in this pass (a bare plural noun could theoretically
        # be a cut-off question) — decided and documented explicitly in known-gaps.md's
        # ambiguous-bare-keywords section rather than added silently: among this taxonomy's
        # actual 34 intents, no other one is plausibly meant by bare "vehicles" (the
        # vehicle-specific LIVE_API intents all need a *specific* vehicle_ref, which a bare
        # plural doesn't suggest), so GET_VEHICLE_ROSTER is the only real candidate.
        "vehicles",
        "my vehicles",
    ],
    "GET_DRIVER_ROSTER": [
        "list all drivers",
        "all drivers",
        "driver list",
        "who drives",
        "show drivers",
        "show me my drivers",
        # Added after live testing: "names of drivers" / "how many drivers" / "list of
        # drivers" / "my drivers" / "who are my drivers" all fell through to OUT_OF_SCOPE —
        # none matched any existing phrase above.
        "names of drivers",
        "how many drivers",
        "list of drivers",
        "my drivers",
        "who are my drivers",
        # Bare "drivers"/"which drivers" — the motivating gap for this whole pass, added via
        # the all-intent systematic probe. Unambiguous for the same reason as "vehicles" above:
        # GET_DRIVER_BEHAVIOR_REPORT always needs a specific driver name + a score/behavior
        # word, so a bare plural noun with neither has only one sensible reading here.
        "drivers",
        "which drivers",
    ],
    # C. Action / write (backlog for v1, still classifiable)
    "CREATE_GEOFENCE": [
        "create a geofence",
        "add a geofence",
        "new geofence",
        "set up a geofence",
        "draw a geofence",
        "make a geofence",
    ],
    "ASSIGN_DRIVER_TO_VEHICLE": [
        "assign driver",
        "assign him to",
        "assign her to",
        "make him the driver of",
        "set the driver for",
        "assign a driver to",
    ],
    "ACKNOWLEDGE_ALERT": [
        "acknowledge the alert",
        "acknowledge alert",
        "mark alert as",
        "dismiss the alert",
        "clear the alert",
        "acknowledge this alert",
        "mark this alert",
        "mark the alert",
    ],
    "SCHEDULE_MAINTENANCE": [
        "schedule a service",
        "book a service",
        "schedule maintenance",
        "arrange a service",
        "set up a service appointment",
    ],
    # D. Knowledge base
    "EXPLAIN_FEATURE": [
        "how does geofencing work",
        "what does the driver score mean",
        "what is geofencing",
        "how does tracking work",
        "explain how",
        # Bare "geofencing" (the gerund/feature-name form) alone — added via the all-intent
        # systematic probe. Deliberately distinct from GET_GEOFENCE_LIST's bare "geofences"
        # above: the gerund ("geofencing") names the *feature/concept*, the plural noun
        # ("geofences") names the *configured zones* — a real, defensible linguistic
        # distinction, not a coin flip. Documented in known-gaps.md.
        "geofencing",
    ],
    "EXPLAIN_ALERT_TYPE": [
        "what counts as",
        "what is harsh braking",
        "harsh braking",
        "why did i get a",
        "what triggers a",
    ],
    "APP_FAQ": [
        "how do i add",
        "how do i register",
        "how do i generate",
        "how do i export",
        "how do i create",
        "how to add",
        "how to register",
        "how to generate",
        # Bare "faq" — added via the all-intent systematic probe. Unambiguous: no other
        # intent's vocabulary references "faq" at all.
        "faq",
    ],
    "TROUBLESHOOTING_DEVICE": [
        "device offline",
        "gps not updating",
        "device shows offline",
        "not connecting",
        "isn't connecting",
        "device not working",
        "gps not working",
        "isn't working",
        "is not updating",
        "isn't updating",
        "device stopped sending",
        # base-tense variant ("why would a device STOP sending...") — the past-tense phrase
        # above doesn't match this; found via the Phase 12 eval golden set.
        "stop sending data",
    ],
    "POLICY_QUESTION": [
        "how long is",
        "data retention",
        "how long do you keep",
        "what happens to my data",
        "retention policy",
        "how long are",
        # Added via the all-intent systematic probe — "privacy policy" is a realistic way to
        # ask about data policy that doesn't mention "retention" at all. Bare "policy" alone is
        # unambiguous: no other intent's vocabulary uses it.
        "privacy policy",
        "policy",
    ],
    "PRICING": [
        "how much does",
        "cost per month",
        "the price",
        "pricing for",
        "plan cost",
        "discount for",
        "how much is the",
        # "what's included in the Enterprise plan?" has none of "cost"/"price"/"pricing" at
        # all — a realistic way to ask about a paid plan's contents. Found via the Phase 12
        # eval golden set.
        "included in the",
    ],
    # E. Conversational / meta
    "GREETING": ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "yo"],
    "GOODBYE": [
        "bye",
        "goodbye",
        "see you",
        "that's all thanks",
        "thank you bye",
        "that's all for now",
        "gotta go",
    ],
    "CHITCHAT": ["how are you", "what can you do", "who are you", "tell me a joke", "what's up", "you're funny", "lol"],
    # Short, unambiguous phrasings — the broader "what is/does X" shape lives in
    # TRIGGER_COOCCURRENCE below, since self-identity questions have too many natural
    # rewordings for a fixed phrase list alone (same reasoning as EXPLAIN_FEATURE/
    # EXPLAIN_ALERT_TYPE). "is track91 a" specifically covers "is Track91 a GPS app?" —
    # bare "is" would be far too generic to add as its own trigger.
    "ABOUT_TRACK91": [
        "is track91 a",
        "your company name",
        "what kind of company",
        "tell me about track91",
        # Added via the all-intent systematic probe. Bare "track91" is unambiguous — no other
        # intent's vocabulary references the product name at all. "who built/made/created this"
        # kept as literal 3-word phrases rather than generalized into TRIGGER_COOCCURRENCE
        # below: a bare "this" subject would be far too generic to add domain-wide.
        "track91",
        "who built this",
        "who made this",
        "who created this",
    ],
}

# Loose plate-shaped span — same separator tolerance as app/nlu/normalization.py /
# app/nlu/entity_extractor.py's own candidate regex, duplicated here (not imported) because
# this module has no dependency on entity_extractor and the two are allowed to drift slightly
# apart without breaking anything — this one only needs to detect "something plate-shaped is
# here", not validate it.
_PLATE_SPAN = r"[A-Za-z]{2}[\s\-.]?\d{2}[\s\-.]?[A-Za-z]{1,2}[\s\-.]?\d{4}"

# Optional possessive between a plate and the topic noun that follows it — "MH12AB1234 speed"
# and "MH12AB1234's speed" are equally natural; found live (after initially only handling this
# for GET_VEHICLE_LOCATION) that "MH12AB1234's fuel" fell through while "MH12AB1234 fuel"
# didn't, from the exact same oversight. Applied uniformly below rather than per-intent now.
_OPTIONAL_POSSESSIVE = r"['’]?s?\s+"

TRIGGER_REGEXES: dict[str, list[re.Pattern]] = {
    # "alert" is mandatory here, not optional — "what does X mean" alone must NOT match (it
    # would otherwise swallow general-knowledge term questions like "what does AIS-140 mean?").
    "EXPLAIN_ALERT_TYPE": [re.compile(r"what does .+ alert mean")],
    "PRICING": [re.compile(r"\bcost\b"), re.compile(r"\bprice\b"), re.compile(r"\bpricing\b")],
    # \w+ alone only matches a single word — "Assign Ramesh Kumar to MH12AB1234" (a two-word
    # name) never matched. Found via the Phase 12 eval golden set, not by inspection.
    "ASSIGN_DRIVER_TO_VEHICLE": [re.compile(r"\bassign (\w+\s?){1,3}to\b")],
    "ACKNOWLEDGE_ALERT": [re.compile(r"\backnowledge .*alert"), re.compile(r"\bmark (this |the )?alert\b")],
    # A bare "<plate> speed"/"<plate>'s location"/"<plate> fuel" has no verb at all for
    # TRIGGER_COOCCURRENCE's verb-list side to match — a genuinely different utterance shape
    # (noun phrase, not a question) than "how fast is it going". Found via the systematic
    # 41-probe realistic-paraphrase check (all three of these intents' cooccurrence tables
    # below were added for the *verb-phrase* shape; this regex covers the *bare-plate* shape
    # neither the old phrase lists nor the new cooccurrence tables reach).
    "GET_VEHICLE_LOCATION": [
        re.compile(_PLATE_SPAN + _OPTIONAL_POSSESSIVE + r"location\b"),
        re.compile(r"\blocate\b"),
        # "can you find MH12AB1234" — "find" alone is too generic a bare phrase to add
        # domain-wide (real false-positive risk outside this closed intent set), but "find" +
        # a plate-shaped token together is unambiguous.
        re.compile(r"\b(find|track)\b.*" + _PLATE_SPAN),
    ],
    "GET_VEHICLE_SPEED": [re.compile(_PLATE_SPAN + _OPTIONAL_POSSESSIVE + r"speed\b")],
    "GET_VEHICLE_FUEL_LEVEL": [
        re.compile(_PLATE_SPAN + _OPTIONAL_POSSESSIVE + r"fuel\b"),
        re.compile(r"\bfuel (percentage|level)\s+of\b"),
    ],
    # Same bare-plate-plus-topic-noun shape, added via the all-intent systematic probe:
    # "MH12AB1234 diagnostics", "MH12AB1234 ignition" have no verb for TRIGGER_COOCCURRENCE's
    # verb-list side to match.
    "GET_VEHICLE_HEALTH": [
        re.compile(_PLATE_SPAN + _OPTIONAL_POSSESSIVE + r"(health|healthy|diagnostics?)\b"),
        # Topic-word-before-plate shape ("any problems with MH12AB1234") — same reasoning as
        # GET_VEHICLE_LOCATION's find/track regex above: the cooccurrence table's subject list
        # only has generic nouns (vehicle/it/...), not a plate, so "problems with <plate>"
        # falls through both the phrase list and cooccurrence alike without this.
        re.compile(r"\b(any )?(issues?|problems?)\s+with\b.*" + _PLATE_SPAN),
    ],
    "GET_VEHICLE_IGNITION_STATUS": [re.compile(_PLATE_SPAN + _OPTIONAL_POSSESSIVE + r"ignition\b")],
}

# Order-independent co-occurrence check: score if the utterance contains AT LEAST ONE phrase
# from each list, anywhere, in any order — not adjacent, not a fixed sentence structure.
# Replaces an earlier fixed-phrase/regex-only approach for these two intents, which proved too
# rigid: a single fixed pattern per intent either over-matched general-knowledge questions
# ("how does GPS triangulation work?") or under-matched realistic rephrasings ("What's
# geofencing?", "Can you tell me how geofencing works?", "Can you explain what the panic alert
# means?") — both failure modes were caught empirically, not assumed.
TRIGGER_COOCCURRENCE: dict[str, tuple[list[str], list[str]]] = {
    "EXPLAIN_FEATURE": (
        # "what happens" added via the Phase 12 eval golden set: "What happens when a vehicle
        # enters or exits a geofence?" is a realistic feature-behavior question that none of
        # the other verb phrases catch.
        ["how does", "how do", "what is", "what's", "what happens", "explain", "tell me", "understand how", "used for"],
        [
            "geofencing",
            "geofence",
            "tracking",
            "driver scoring",
            "driver score",
            "alert system",
            "maintenance reminder",
            "live status",
        ],
    ),
    "EXPLAIN_ALERT_TYPE": (
        ["what does", "what is", "why did i get", "why would i", "why did i receive", "explain"],
        [
            "alert",
            "harsh braking",
            "harsh acceleration",
            "speeding",
            "panic",
            "low fuel",
            "geofence entry",
            "geofence exit",
            "idle",
            "device offline",
        ],
    ),
    # Added after the systematic 41-probe realistic-paraphrase check found the plain
    # TRIGGER_PHRASES lists for these four intents only cover a handful of exact phrasings —
    # e.g. "is MH12AB1234 healthy" and "MH12AB1234's fuel percentage" both fell through
    # entirely. Scoped to the highest-traffic intents first (location/speed/fuel/driver
    # roster); the remaining LIVE_API/MONGO_REPO intents have the same shape of gap, tracked
    # in docs/phase-6-semantic-analysis/known-gaps.md rather than fixed here.
    "GET_VEHICLE_LOCATION": (
        ["where is", "where's", "locate", "find", "track", "current location", "location of", "where can i find"],
        ["vehicle", "truck", "van", "car", "fleet", "it"],
    ),
    "GET_VEHICLE_SPEED": (
        # "how quick" (no "-ly") added via the all-intent systematic probe.
        ["how fast", "how quick", "how quickly", "speed", "going at what speed", "what speed"],
        ["vehicle", "truck", "van", "car", "it", "moving", "going"],
    ),
    "GET_VEHICLE_FUEL_LEVEL": (
        ["fuel", "petrol", "gas", "how much"],
        # "status" added via the all-intent systematic probe — "fuel status of MH12AB1234"
        # fell through with neither this nor the bare-plate regex reaching it (the regex only
        # covers "fuel" appearing directly after the plate, not "status of" in between).
        ["level", "left", "remaining", "percentage", "have", "does it have", "status", "vehicle", "truck", "van", "car"],
    ),
    "GET_DRIVER_ROSTER": (
        # "name of"/"list of" (singular, with "of") added after live testing — "name of
        # driver" and "list of driver" fell through the same way "how many drivers" did
        # before, just a singular-noun variant neither the verb nor subject list caught. Bare
        # singular "driver" was tried as a subject word first and reverted: it collided with
        # GET_DRIVER_BEHAVIOR_REPORT ("show me the driver scorecard" started misclassifying as
        # GET_DRIVER_ROSTER, caught by the existing paraphrase test suite) — "of driver" is
        # specific enough to catch the singular-with-"of" phrasing without that collision.
        ["list", "show", "who are", "how many", "names of", "name of", "give me"],
        ["drivers", "of driver", "driver list", "driver roster"],
    ),
    # --- Everything below was added in the all-intent systematic probe pass (see
    # docs/phase-6-semantic-analysis/known-gaps.md) that closed out the remaining
    # LIVE_API/MONGO_REPO/backlog/KB gaps this table's docstring originally tracked as "not yet
    # fixed" — same recipe as the four intents above (verb-list x subject-list), one intent at
    # a time, each re-verified against the full paraphrase suite before moving to the next. ---
    "GET_VEHICLE_HEALTH": (
        # Bare "is" was tried here first and reverted: "is" alone is so generic (a huge share
        # of yes/no questions start with it) that combined with a merely-plausible subject word
        # like "it", it stole "How quick is it moving right now" from GET_VEHICLE_SPEED —
        # caught by re-running the full probe suite after adding this table, not by inspection.
        # "is it healthy"/"is the vehicle healthy" as specific multi-word verb entries avoid
        # that trap while still catching the realistic phrasing.
        ["is it healthy", "is the vehicle healthy", "any issues with", "any problems with", "check", "run a diagnostic on"],
        ["healthy", "engine", "diagnostic", "ok"],
    ),
    "GET_VEHICLE_IGNITION_STATUS": (
        # Bare "is" reverted for the same reason as GET_VEHICLE_HEALTH above — "turned on"/
        # "turned off" are specific enough on their own to not need it. Bare "running" tried in
        # BOTH lists first and reverted too: self-pairing on that one word alone made "Is
        # MH12AB1234's engine ok and running smoothly?" (a health question) wrongly register a
        # second, phantom GET_VEHICLE_IGNITION_STATUS intent — caught by the dual-intent
        # false-positive eval (app/eval/second_intent_eval.py), not by inspection. Already fully
        # covered by the existing literal "is it running" TRIGGER_PHRASES entry above, so
        # nothing is lost by dropping it here.
        ["turned on", "turned off", "is it on", "is it off"],
        ["on", "off", "ignition", "engine", "moving", "parked"],
    ),
    "GET_FLEET_LIVE_STATUS": (
        ["what's my", "what is my", "number of", "how many", "current"],
        ["fleet", "vehicles moving", "vehicles active", "fleet status"],
    ),
    "GET_TRIP_HISTORY": (
        ["trips", "journeys", "journey", "where has", "where did", "been"],
        ["made", "did", "today", "yesterday", "history", "this week"],
    ),
    "GET_TRIP_SUMMARY": (
        ["how far", "total", "how many km", "how much distance"],
        ["travel", "travelled", "traveled", "covered", "cover", "this week", "this month"],
    ),
    "GET_ALERT_HISTORY": (
        ["what alerts", "any alerts", "alerts for", "alerts happened"],
        ["today", "happened", "this week", "this month", "yesterday"],
    ),
    "GET_MAINTENANCE_HISTORY": (
        # Deliberately past-tense-only verbs ("service records", "when was", "last") — kept
        # disjoint from GET_MAINTENANCE_DUE's forward-looking verbs (due/overdue/upcoming) and
        # SCHEDULE_MAINTENANCE's action verbs (schedule/book/arrange) below, per
        # known-gaps.md's warning that these three genuinely share vocabulary ("service"/
        # "maintenance") and need an explicit disambiguating check, not a blind shared list.
        ["service records", "maintenance log", "when was", "last"],
        ["serviced", "service", "maintenance", "records", "log"],
    ),
    "GET_MAINTENANCE_DUE": (
        ["due", "overdue", "need", "needs", "upcoming"],
        ["service", "servicing", "maintenance"],
    ),
    "GET_DRIVER_BEHAVIOR_REPORT": (
        # "score" was tried in BOTH lists first and reverted: on an utterance that also
        # contains the literal 2-word TRIGGER_PHRASES entry "driver score", it double-counted
        # (phrase match + cooccurrence self-pairing) to a 6 that tied — and, checked first by
        # category order, beat — EXPLAIN_FEATURE's genuine 6 on "What does the driver score
        # mean?". Caught by re-running the full paraphrase test suite, not by inspection.
        # Keeping "score" as a verb only (paired with "this month"/"driving" as the subject,
        # not itself) still catches "Ramesh Kumar's score this month" without the self-pairing.
        ["how is", "how's", "driving score", "behavior", "score"],
        ["driving", "this month", "behavior"],
    ),
    "GET_FUEL_CONSUMPTION_REPORT": (
        # Deliberately distinct from GET_VEHICLE_FUEL_LEVEL's cooccurrence above: known-gaps.md
        # already flagged that "how much fuel are we using this month" was misclassifying as
        # GET_VEHICLE_FUEL_LEVEL (whose "how much fuel" TRIGGER_PHRASES entry matched, scoring
        # 2, with nothing outscoring it). This cooccurrence match scores 4 — checked later in
        # priority order (category B vs A) but with a strictly higher score, so it now wins.
        # Confirmed by re-running the exact case from known-gaps.md, not assumed.
        ["fuel usage", "fuel report", "fuel efficiency", "fuel consumption", "mileage", "how much fuel"],
        ["report", "this month", "this week", "overall", "fleet", "efficiency", "average", "using"],
    ),
    "GET_GEOFENCE_LIST": (
        ["what zones", "which zones", "zones apply", "geofences apply"],
        ["apply", "for", "set up"],
    ),
    "GET_VEHICLE_ROSTER": (
        # "how many" was tried here first and reverted: paired with bare "vehicles" it stole
        # "How many vehicles are active now?" from GET_FLEET_LIVE_STATUS — caught by re-running
        # the full paraphrase test suite, not by inspection. "how many" alone doesn't
        # distinguish "list them" from "count the active ones"; "show"/"list"/"give me"/"what"
        # do, without needing it.
        ["show", "list", "give me", "what"],
        ["vehicles", "vehicle list", "my fleet", "fleet roster"],
    ),
    "CREATE_GEOFENCE": (
        # "zone"/"boundary"/"perimeter" as geofence synonyms — a realistic way to ask for one
        # without the word "geofence" at all. Safe against GET_GEOFENCE_LIST (which has no
        # "zone"/"boundary" vocabulary of its own) since this still requires a CREATE-shaped
        # verb, which a browsing/listing question never contains.
        ["create", "add", "new", "set up", "draw", "make", "need a"],
        ["geofence", "zone", "boundary", "perimeter"],
    ),
    "ACKNOWLEDGE_ALERT": (
        ["acknowledge", "resolve", "dismiss", "clear", "close", "mark"],
        ["alert"],
    ),
    "SCHEDULE_MAINTENANCE": (
        ["schedule", "book", "arrange", "set up", "need"],
        ["service", "maintenance", "appointment", "oil change"],
    ),
    "APP_FAQ": (
        ["how do i", "how to", "steps to", "can i", "is it possible to"],
        ["add", "register", "generate", "export", "create", "import", "download", "update", "change", "delete"],
    ),
    "TROUBLESHOOTING_DEVICE": (
        # Bare "offline" was tried here first and reverted: paired with "device" it outscored
        # (2 phrase + 4 cooccurrence = 6) EXPLAIN_ALERT_TYPE's genuine cooccurrence match (4) on
        # "What is a device offline alert?" — a question about what the alert MEANS, not a
        # report of an actual problem. Caught by re-running the full paraphrase test suite, not
        # by inspection. "going offline" is specific enough to catch the real target case
        # ("Device keeps going offline") without swallowing the alert-type question.
        ["going offline", "not connecting", "not working", "not updating", "stopped sending", "no signal", "not sending"],
        ["device", "gps", "tracker", "signal"],
    ),
    # Added after real testing: "what is Track91" / "what does your company do" / "is Track91
    # a GPS app?" were previously refused (OUT_OF_SCOPE) or — worse — answered by
    # GENERAL_KNOWLEDGE with a generic "GPS apps in general" answer, since GENERAL_KNOWLEDGE
    # has zero positive triggers of its own and is only ever reached as a last-resort fallback
    # (DOMAIN_ADJACENT_KEYWORDS below) once nothing else scores. Any real trigger match here
    # therefore automatically outranks that fallback — no separate "priority" mechanism is
    # needed beyond having triggers that fire at all.
    "ABOUT_TRACK91": (
        ["what is", "what's", "what does", "tell me about", "what kind of"],
        ["track91", "your company", "this platform", "this app"],
    ),
}

AFFIRM_DENY_PHRASES = [
    "yes",
    "yeah",
    "yep",
    "correct",
    "that one",
    "that's right",
    "no",
    "nope",
    "not that one",
    "the other one",
    "wrong one",
]

DOMAIN_ADJACENT_KEYWORDS = [
    "gps",
    "fleet",
    "vehicle",
    "tracking",
    "telematics",
    "ais-140",
    "ais 140",
    "odometer",
    "geofenc",
    "obd",
    "sim",
    "device",
]
