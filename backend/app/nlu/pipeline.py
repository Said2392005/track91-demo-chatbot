"""
Combines intent classification + entity extraction + the CLARIFICATION_NEEDED decision into
the single "Semantic Analysis" result Phase 9's router will consume — matching the Phase 2
component diagram's node order (Intent Classifier -> Entity Extractor/Coreference Resolver).

CLARIFICATION_NEEDED is decided here, not inside the classifier: from the raw utterance alone,
"what's its speed?" IS clearly GET_VEHICLE_SPEED — it only becomes a clarification case once
entity resolution fails to find an active vehicle to resolve "its" against. This matches
intent-taxonomy.md's own note that CLARIFICATION_NEEDED depends on more than the utterance.

Resuming a pending clarification (found via real testing: "where is my vehicle?" -> "which
vehicle?" -> a bare "MH12AB1234" with no verb fell through to OUT_OF_SCOPE instead of
completing GET_VEHICLE_LOCATION) is handled here too, for the same reason: it's not something
the classifier alone can decide, and it's a variant of the same
classify-then-extract-then-decide shape this function already owns. `session_state[
"pending_clarification"]` (set by clarify_node, popped once by entry_node — see
SessionRepository.set_pending_clarification/pop_pending_clarification) records which intent was
waiting and on what. If the freshly-classified intent is a no-clear-trigger fallback
(OUT_OF_SCOPE/GENERAL_KNOWLEDGE) AND re-running extraction against the *pending* intent resolves
the specific thing that was missing, that pending intent is resumed instead of the fallback —
the classifier's own fresh verdict is not trusted blindly when there's a more specific
explanation for a low-signal utterance. A message that's clearly a new request (matches its own
trigger phrase) is never overridden this way, since raw_intent then won't be OUT_OF_SCOPE/
GENERAL_KNOWLEDGE in the first place.

Dual-intent detection (Q2's "middle option" from the multi-intent tradeoff discussion) also
lives here, gated deliberately narrow: only attempted once the primary intent has already
resolved cleanly (final_intent == raw_intent) and is a real, actionable, non-backlog intent —
never for a primary that itself needs clarification, and never for meta/backlog primaries. See
app/nlu/second_intent.py's docstring for why this is score-based (reusing the classifier's own
trigger scoring) rather than text-splitting, and app/eval/second_intent_eval.py for the measured
0% false-positive / 100% true-positive rates (on detectable cases) that justified wiring this
in, after Approach 1 (conjunction-splitting) was measured and rejected.
"""

from dataclasses import dataclass, field
from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.taxonomy import INTENT_SPECS
from app.nlu.entity_extractor import ExtractionResult, extract_entities, resolve_first_message_bare_last4
from app.nlu.intent_classifier import IntentClassifier
from app.nlu.second_intent import detect_second_intent


@dataclass
class AnalysisResult:
    raw_intent: str
    final_intent: str
    entities: dict
    unresolved_required: list[str]
    ambiguous: dict
    secondary_raw_intent: str | None = None
    secondary_entities: dict = field(default_factory=dict)
    secondary_unresolved_required: list[str] = field(default_factory=list)
    secondary_ambiguous: dict = field(default_factory=dict)


_FALLBACK_INTENTS = ("OUT_OF_SCOPE", "GENERAL_KNOWLEDGE")


async def analyze(
    utterance: str,
    classifier: IntentClassifier,
    company_id: ObjectId,
    db: AsyncIOMotorDatabase,
    session_state: dict | None = None,
    now: datetime | None = None,
) -> AnalysisResult:
    session_state = session_state or {}
    pending = session_state.get("pending_clarification")

    # awaiting_clarification drives RuleBasedIntentClassifier's AFFIRM_DENY check — real
    # "Yes"/"No" replies to a real clarifying question now correctly classify as AFFIRM_DENY
    # instead of falling through to OUT_OF_SCOPE, since this flag is finally driven by real
    # session state rather than only ever set manually in tests/the eval golden set.
    raw_intent = await classifier.classify(utterance, {**session_state, "awaiting_clarification": pending is not None})

    extraction: ExtractionResult | None = None
    if pending and raw_intent in _FALLBACK_INTENTS:
        resumed_extraction = await extract_entities(
            utterance,
            pending["intent"],
            company_id,
            db,
            active_entities=session_state.get("active_entities"),
            now=now,
            # Only when we already know the previous turn was specifically waiting on a
            # vehicle_ref (either the plain "which vehicle?" question or the multi-vehicle list)
            # — a bare 4-digit reply is only meaningful as a plate fragment in that context, not
            # as general free-text entity extraction. See entity_extractor.py's _LAST4_RE.
            resolve_vehicle_by_last4=(pending["missing"] == "vehicle_ref"),
        )
        fully_resolved = (
            pending["missing"] not in resumed_extraction.unresolved_required
            and pending["missing"] not in resumed_extraction.ambiguous
        )
        # A last4-digit reply that collides with more than one of the company's own vehicles
        # isn't a failed resume — it's real progress (narrowed from "all N vehicles" down to
        # just the colliding ones) that deserves its own follow-up question, not a silent fall-
        # through to OUT_OF_SCOPE. Scoped narrowly to this one case, not "any still-ambiguous
        # entity resumes": driver_ref's pre-existing ambiguous-on-resume behavior (fall through,
        # don't resume) is intentionally left unchanged.
        narrowed_to_vehicle_collision = pending["missing"] == "vehicle_ref" and (
            resumed_extraction.ambiguous.get("vehicle_ref", {}).get("reason") == "last4_collision"
        )
        if fully_resolved or narrowed_to_vehicle_collision:
            raw_intent = pending["intent"]
            extraction = resumed_extraction

    if extraction is None and not pending and raw_intent == "OUT_OF_SCOPE":
        # A bare 4-digit FIRST message (no pending clarification, nothing else classified)
        # might still identify a real vehicle by its plate's last 4 digits, even with zero
        # verb/keyword to classify an intent from at all. Checked against this company's own
        # vehicles — deliberately does NOT guess which *intent* the user wants (e.g. default to
        # GET_VEHICLE_LOCATION): rejected on purpose, since a bare number gives no signal
        # narrowing down which of ~10 vehicle-specific intents is meant, and a wrong-but-
        # confident answer is worse than asking. GENERAL_KNOWLEDGE is deliberately excluded
        # from this check (unlike _FALLBACK_INTENTS above): it only ever fires when a domain
        # keyword matched, which a bare 4-digit utterance never contains, so it can't reach
        # here anyway. See app/router/clarification.py's "identified_no_intent" question and
        # app/router/router.py's route(), which special-cases this the same way the existing
        # last4-collision path is special-cased (both keyed off ambiguous["vehicle_ref"]'s
        # "reason", so no new state field or nodes.py change was needed for this).
        resolution = await resolve_first_message_bare_last4(utterance, company_id, db)
        if resolution.vehicle is not None:
            extraction = ExtractionResult(
                entities={"vehicle_id": resolution.vehicle["_id"]},
                ambiguous={"vehicle_ref": {"reason": "identified_no_intent", "candidates": [resolution.vehicle]}},
            )
        elif resolution.ambiguous is not None:
            extraction = ExtractionResult(ambiguous={"vehicle_ref": resolution.ambiguous})

    spec = INTENT_SPECS.get(raw_intent)
    if spec is None or spec.subsystem == "NONE":
        if extraction is not None and (extraction.entities or extraction.ambiguous):
            # Only reachable via the bare-last4-first-message branch above — raw_intent stays
            # OUT_OF_SCOPE (there's no real intent to swap it to), but a vehicle was resolved or
            # collided on, so this must still become a real clarification turn rather than
            # following the normal NONE-subsystem short-circuit. The extra truthiness check
            # (not just `extraction is not None`) matters: a *resumed* pending_clarification
            # whose intent happens to be OUT_OF_SCOPE (only reachable via this same new feature,
            # one turn later — e.g. the user's second bare-digit reply) produces a real but
            # EMPTY ExtractionResult() from the unrelated resume branch above, which must fall
            # through to the plain OUT_OF_SCOPE case below, not be mistaken for this one. Found
            # by tracing the resume path deliberately, not by inspection.
            return AnalysisResult(raw_intent, "CLARIFICATION_NEEDED", extraction.entities, [], extraction.ambiguous)
        return AnalysisResult(raw_intent, raw_intent, {}, [], {})

    if extraction is None:
        extraction = await extract_entities(
            utterance,
            raw_intent,
            company_id,
            db,
            active_entities=session_state.get("active_entities"),
            now=now,
        )

    final_intent = raw_intent
    if extraction.unresolved_required or extraction.ambiguous:
        final_intent = "CLARIFICATION_NEEDED"

    secondary_raw_intent: str | None = None
    secondary_entities: dict = {}
    secondary_unresolved_required: list[str] = []
    secondary_ambiguous: dict = {}
    if final_intent == raw_intent and spec.mvp:
        candidate = detect_second_intent(utterance, raw_intent)
        candidate_spec = INTENT_SPECS.get(candidate) if candidate else None
        if candidate_spec is not None and candidate_spec.subsystem != "NONE" and candidate_spec.mvp:
            secondary_extraction = await extract_entities(
                utterance,
                candidate,
                company_id,
                db,
                active_entities=session_state.get("active_entities"),
                now=now,
            )
            secondary_raw_intent = candidate
            secondary_entities = secondary_extraction.entities
            secondary_unresolved_required = secondary_extraction.unresolved_required
            secondary_ambiguous = secondary_extraction.ambiguous

    return AnalysisResult(
        raw_intent=raw_intent,
        final_intent=final_intent,
        entities=extraction.entities,
        unresolved_required=extraction.unresolved_required,
        ambiguous=extraction.ambiguous,
        secondary_raw_intent=secondary_raw_intent,
        secondary_entities=secondary_entities,
        secondary_unresolved_required=secondary_unresolved_required,
        secondary_ambiguous=secondary_ambiguous,
    )
