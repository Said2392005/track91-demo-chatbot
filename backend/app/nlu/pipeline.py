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
"""

from dataclasses import dataclass
from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.taxonomy import INTENT_SPECS
from app.nlu.entity_extractor import ExtractionResult, extract_entities
from app.nlu.intent_classifier import IntentClassifier


@dataclass
class AnalysisResult:
    raw_intent: str
    final_intent: str
    entities: dict
    unresolved_required: list[str]
    ambiguous: dict


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
        )
        if pending["missing"] not in resumed_extraction.unresolved_required and pending["missing"] not in resumed_extraction.ambiguous:
            raw_intent = pending["intent"]
            extraction = resumed_extraction

    spec = INTENT_SPECS.get(raw_intent)
    if spec is None or spec.subsystem == "NONE":
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

    return AnalysisResult(
        raw_intent=raw_intent,
        final_intent=final_intent,
        entities=extraction.entities,
        unresolved_required=extraction.unresolved_required,
        ambiguous=extraction.ambiguous,
    )
