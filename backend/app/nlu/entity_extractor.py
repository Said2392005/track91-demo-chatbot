"""
Entity extraction — orchestrates normalization, repository lookups, dictionary matching, the
date parser, and coreference resolution into one (utterance, intent) -> entities call, per the
required/optional entities each intent declares in app/core/taxonomy.py.

`company_id` is a caller-supplied parameter (from auth context), never extracted from text,
per entity-taxonomy.md.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.taxonomy import INTENT_SPECS
from app.db.repositories.driver_repository import DriverRepository
from app.db.repositories.vehicle_repository import VehicleRepository
from app.nlu import coreference
from app.nlu.date_parser import parse_date_range
from app.nlu.dictionaries import (
    ALERT_TYPE_SYNONYMS,
    METRIC_TYPE_SYNONYMS,
    PLAN_TIER_SYNONYMS,
    REPORT_TYPE_SYNONYMS,
    match_dictionary,
)
from app.nlu.normalization import is_valid_plate, normalize_plate_candidate

# Loose plate-shaped span: letters/digits with optional space/hyphen/dot separators — must
# match the same separator set as normalization.normalize_plate_candidate()'s strip regex, or
# a validly-separated plate (e.g. "MH.12.AB.1234") never even gets found as a candidate here.
_PLATE_CANDIDATE_RE = re.compile(
    r"\b[A-Za-z]{2}[\s\-.]?\d{2}[\s\-.]?[A-Za-z]{1,2}[\s\-.]?\d{4}\b"
)

# Capitalized-word-sequence candidates for driver names (1-2 words). Accepted only if a DB
# lookup actually resolves it — a false-positive capitalized word (e.g. a sentence-initial
# "Where") simply fails to resolve and is discarded, so no stoplist is needed for correctness.
_NAME_CANDIDATE_RE = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b")


@dataclass
class ExtractionResult:
    entities: dict = field(default_factory=dict)
    unresolved_required: list[str] = field(default_factory=list)
    ambiguous: dict = field(default_factory=dict)


async def _resolve_vehicle_ref(
    utterance: str, company_id: ObjectId, vehicle_repo: VehicleRepository
) -> dict | None:
    for candidate in _PLATE_CANDIDATE_RE.findall(utterance):
        normalized = normalize_plate_candidate(candidate)
        if is_valid_plate(normalized):
            vehicle = await vehicle_repo.find_by_plate_number(company_id, normalized)
            if vehicle:
                return vehicle
    return await vehicle_repo.find_by_nickname_containing(company_id, utterance)


async def _resolve_driver_ref(
    utterance: str, company_id: ObjectId, driver_repo: DriverRepository
) -> tuple[dict | None, list[dict]]:
    """Returns (resolved_driver_or_None, all_candidates_if_ambiguous)."""
    for candidate in _NAME_CANDIDATE_RE.findall(utterance):
        matches = await driver_repo.find_by_name(company_id, candidate)
        if len(matches) == 1:
            return matches[0], []
        if len(matches) > 1:
            return None, matches
    return None, []


async def extract_entities(
    utterance: str,
    intent: str,
    company_id: ObjectId,
    db: AsyncIOMotorDatabase,
    active_entities: dict | None = None,
    now: datetime | None = None,
) -> ExtractionResult:
    now = now or datetime.now(timezone.utc)
    spec = INTENT_SPECS.get(intent)
    result = ExtractionResult()
    if spec is None:
        return result

    vehicle_repo = VehicleRepository(db)
    driver_repo = DriverRepository(db)

    wanted = set(spec.required) | set(spec.optional) | set(spec.required_one_of)

    if "vehicle_ref" in wanted:
        vehicle = await _resolve_vehicle_ref(utterance, company_id, vehicle_repo)
        if vehicle is None and coreference.contains_pronoun_reference(utterance):
            active_id = coreference.resolve_active_entity("vehicle", active_entities)
            if active_id:
                result.entities["vehicle_id"] = active_id
        elif vehicle is not None:
            result.entities["vehicle_id"] = vehicle["_id"]

    if "driver_ref" in wanted:
        driver, candidates = await _resolve_driver_ref(utterance, company_id, driver_repo)
        if candidates:
            result.ambiguous["driver_ref"] = candidates
        elif driver is not None:
            result.entities["driver_id"] = driver["_id"]
        elif coreference.contains_pronoun_reference(utterance):
            active_id = coreference.resolve_active_entity("driver", active_entities)
            if active_id:
                result.entities["driver_id"] = active_id

    if "date_range" in wanted:
        date_range = parse_date_range(utterance, now, settings.default_timezone)
        if date_range:
            result.entities["date_range"] = date_range

    if "alert_type" in wanted:
        alert_type = match_dictionary(utterance, ALERT_TYPE_SYNONYMS)
        if alert_type:
            result.entities["alert_type"] = alert_type

    if "metric_type" in wanted:
        metric_type = match_dictionary(utterance, METRIC_TYPE_SYNONYMS)
        if metric_type:
            result.entities["metric_type"] = metric_type

    if "fleet_group_ref" in wanted:
        groups = await vehicle_repo.list_fleet_groups(company_id)
        lowered = utterance.lower()
        for group in groups:
            if group.lower() in lowered:
                result.entities["fleet_group_ref"] = group
                break

    if "geofence_ref" in wanted:
        from app.db.repositories.geofence_repository import GeofenceRepository

        # No dictionary of geofence names to scan against without a full-text pass; left as a
        # direct-name lookup only. Free-text geofence NER is out of scope until geofence intents
        # (largely backlog, per intent-taxonomy.md section C) need it.
        geofence_repo = GeofenceRepository(db)
        for candidate in _NAME_CANDIDATE_RE.findall(utterance):
            geofence = await geofence_repo.find_by_name(company_id, candidate)
            if geofence:
                result.entities["geofence_id"] = geofence["_id"]
                break

    if "report_type" in wanted:
        report_type = match_dictionary(utterance, REPORT_TYPE_SYNONYMS)
        if report_type:
            result.entities["report_type"] = report_type

    if "plan_tier_ref" in wanted:
        plan_tier = match_dictionary(utterance, PLAN_TIER_SYNONYMS)
        if plan_tier:
            result.entities["plan_tier_ref"] = plan_tier

    if "kb_topic" in wanted:
        result.entities["kb_topic"] = utterance.strip()

    for required in spec.required:
        entity_key = "vehicle_id" if required == "vehicle_ref" else required
        entity_key = "driver_id" if required == "driver_ref" else entity_key
        entity_key = "geofence_id" if required == "geofence_ref" else entity_key
        if entity_key not in result.entities and required not in result.ambiguous:
            result.unresolved_required.append(required)

    if spec.required_one_of:
        satisfied = any(
            ("vehicle_id" if r == "vehicle_ref" else "driver_id" if r == "driver_ref" else r) in result.entities
            for r in spec.required_one_of
        )
        if not satisfied:
            result.unresolved_required.append("one_of:" + "|".join(spec.required_one_of))

    return result
