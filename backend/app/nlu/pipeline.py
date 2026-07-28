"""
Combines intent classification + entity extraction + the CLARIFICATION_NEEDED decision into
the single "Semantic Analysis" result Phase 9's router will consume — matching the Phase 2
component diagram's node order (Intent Classifier -> Entity Extractor/Coreference Resolver).

CLARIFICATION_NEEDED is decided here, not inside the classifier: from the raw utterance alone,
"what's its speed?" IS clearly GET_VEHICLE_SPEED — it only becomes a clarification case once
entity resolution fails to find an active vehicle to resolve "its" against. This matches
intent-taxonomy.md's own note that CLARIFICATION_NEEDED depends on more than the utterance.
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


async def analyze(
    utterance: str,
    classifier: IntentClassifier,
    company_id: ObjectId,
    db: AsyncIOMotorDatabase,
    session_state: dict | None = None,
    now: datetime | None = None,
) -> AnalysisResult:
    session_state = session_state or {}
    raw_intent = await classifier.classify(utterance, session_state)

    spec = INTENT_SPECS.get(raw_intent)
    if spec is None or spec.subsystem == "NONE":
        return AnalysisResult(raw_intent, raw_intent, {}, [], {})

    extraction: ExtractionResult = await extract_entities(
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
