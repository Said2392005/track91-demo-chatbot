"""
Vehicle registration normalization — the single implementation of the rule defined in
docs/phase-1-planning/entity-taxonomy.md and locked into the Phase 2 sequence diagrams
("normalization happens ONCE, in entity extraction, before the Router ever sees it").
"""

import re

from app.db.schema_definitions import VEHICLE_PLATE_PATTERN

_PLATE_REGEX = re.compile(VEHICLE_PLATE_PATTERN)
_SEPARATOR_REGEX = re.compile(r"[\s\-.]")


def normalize_plate_candidate(raw: str) -> str:
    """strip -> uppercase -> remove separators. Does not validate the result — call
    is_valid_plate() separately, since a normalized non-plate string (e.g. a nickname) is a
    legitimate outcome, not an error."""
    text = raw.strip().upper()
    return _SEPARATOR_REGEX.sub("", text)


def is_valid_plate(normalized: str) -> bool:
    return bool(_PLATE_REGEX.fullmatch(normalized))
