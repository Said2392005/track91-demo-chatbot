"""
Coreference resolution — resolves pronoun references ("it", "its", "that one") against the
session's active-entity state.

Phase 8 owns *persisting* active-entity state across turns (session store, LangGraph
checkpointer); this module only owns the *resolution algorithm* given whatever active-entity
state is passed in — it has no storage of its own, by design, per the split documented in
docs/phase-1-planning/entity-taxonomy.md ("Phase 8 owns the active-entity tracker...").
"""

import re

_PRONOUN_PATTERN = re.compile(
    r"\b(it|its|it's|that one|this one|that|this|them|they|their|theirs)\b", re.IGNORECASE
)

# entity_type -> active_entities key
_ACTIVE_ENTITY_KEYS = {
    "vehicle": "vehicle_id",
    "driver": "driver_id",
    "geofence": "geofence_id",
}

# Generic entity-type-referring nouns — used only to detect when an utterance explicitly names
# a DIFFERENT entity type than the one a memory-fill would otherwise substitute. Real bug,
# found live: "where is my driver" (in a session with an already-active vehicle) classified as
# GET_VEHICLE_LOCATION via the bare "where is" phrase; Phase 6 correctly left vehicle_ref
# unresolved (no pronoun in "my driver"), but app/router/router.py's own *unconditional*
# active-entity fallback filled in the stale vehicle anyway — producing a confident,
# specific-sounding but wrong-context GPS answer instead of asking which driver/vehicle. Worse
# than a decline: it looked like a real answer.
_ENTITY_TYPE_WORDS = {
    "vehicle_id": re.compile(r"\b(vehicle|truck|van|car|fleet)\b", re.IGNORECASE),
    "driver_id": re.compile(r"\b(driver|drivers)\b", re.IGNORECASE),
    "geofence_id": re.compile(r"\b(geofence|geofences|zone|zones)\b", re.IGNORECASE),
}


def contains_pronoun_reference(text: str) -> bool:
    return bool(_PRONOUN_PATTERN.search(text))


def resolve_active_entity(entity_type: str, active_entities: dict | None) -> str | None:
    """entity_type: 'vehicle' | 'driver' | 'geofence'. Returns the active entity's ID (as
    stored in session state) or None if nothing is active for that type."""
    if not active_entities:
        return None
    key = _ACTIVE_ENTITY_KEYS.get(entity_type)
    if key is None:
        return None
    return active_entities.get(key)


def filter_active_entities_by_mentioned_type(utterance: str, active_entities: dict | None) -> dict:
    """If the utterance explicitly names an entity type ("driver"), only active entities of
    that type stay eligible for a memory-fill — an active vehicle from an earlier turn must
    not silently answer a question that's actually about a driver. If the utterance names no
    entity type at all (e.g. "where is my vehicle", "what's its speed" — the cases router.py's
    memory-fill exists for), nothing is filtered. This only ever narrows what memory-fill can
    use, never expands it — a text-aware gate applied by the caller (router_node), not inside
    route() itself, which stays pure/text-blind per ADR 003."""
    active_entities = active_entities or {}
    mentioned = {key for key, pattern in _ENTITY_TYPE_WORDS.items() if pattern.search(utterance)}
    if not mentioned:
        return active_entities
    return {k: v for k, v in active_entities.items() if k in mentioned}
