"""
Active-entity tracker — the TTL-aware layer on top of SessionRepository that Phase 6's
coreference resolution (app/nlu/coreference.py, app/nlu/pipeline.py) reads from.

Phase 6 built the *resolution algorithm* against a plain `active_entities` dict and explicitly
deferred persistence to Phase 8 (see entity-taxonomy.md). This module is that persistence layer
— it owns two things Phase 6 didn't: where active_entities is stored (SessionRepository /
Mongo), and the expiry rule (settings.active_entity_ttl_seconds) that makes "its speed" stop
resolving to a vehicle discussed long enough ago that the reference is more likely to confuse
than help, even within an otherwise-still-open session.
"""

from datetime import datetime, timezone

from bson import ObjectId

from app.core.config import settings
from app.db.repositories.session_repository import SessionRepository

ENTITY_TYPES = ("vehicle", "driver", "geofence")


async def get_active_entities(
    repo: SessionRepository, company_id: ObjectId, session_id: ObjectId, now: datetime | None = None
) -> dict:
    """Returns the session's active_entities dict, or {} if none set or expired. Shaped to
    drop straight into app.nlu.pipeline.analyze()'s session_state={"active_entities": ...}."""
    now = now or datetime.now(timezone.utc)
    active_entities, updated_at = await repo.get_active_entities(company_id, session_id)

    if not active_entities or updated_at is None:
        return {}

    age_seconds = (now - updated_at).total_seconds()
    if age_seconds > settings.active_entity_ttl_seconds:
        return {}

    return active_entities


async def set_active_entity(
    repo: SessionRepository,
    company_id: ObjectId,
    session_id: ObjectId,
    entity_type: str,
    entity_id: ObjectId,
    now: datetime | None = None,
) -> None:
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"Unknown entity_type {entity_type!r}, expected one of {ENTITY_TYPES}")
    now = now or datetime.now(timezone.utc)
    await repo.set_active_entity(company_id, session_id, entity_type, entity_id, now)
