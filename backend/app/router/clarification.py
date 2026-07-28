"""
Fixed clarifying-question templates, keyed by the missing entity requirement. Deterministic —
not LLM-generated — for the same reason routing itself is deterministic (ADR 003): a template
lookup is fast, free, and doesn't need an LLM call to ask "which vehicle?"
"""

_TEMPLATES = {
    "vehicle_ref": "Which vehicle are you asking about? You can give me its registration number.",
    "driver_ref": "Which driver are you asking about? Could you give me their full name?",
    "geofence_ref": "Which geofence are you asking about?",
    "date_range": "What time period would you like — e.g. today, this week, or a specific date range?",
    "one_of:vehicle_ref|driver_ref": "Which vehicle or driver are you asking about?",
}

_DEFAULT = "Could you clarify what you're asking about?"


def clarifying_question(missing: str) -> str:
    return _TEMPLATES.get(missing, _DEFAULT)
