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
