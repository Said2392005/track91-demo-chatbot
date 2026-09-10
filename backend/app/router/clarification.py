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


def _vehicle_list_question(ambiguous_vehicle_ref: dict) -> str:
    """Builds a dynamic clarifying question listing actual plate numbers — the one case this
    module can't answer from a fixed template alone, since the candidate list is per-request
    data (app/nlu/entity_extractor.py's ambiguous["vehicle_ref"], already fetched during entity
    extraction; this function does no I/O of its own, same as the rest of routing/ADR 003)."""
    plates = [v["plate_number"] for v in ambiguous_vehicle_ref["candidates"]]
    plate_list = ", ".join(plates)
    reason = ambiguous_vehicle_ref.get("reason")
    if reason == "last4_collision":
        return (
            f"More than one of your vehicles matches those last 4 digits: {plate_list}. "
            "Which one did you mean? You can reply with the full registration number."
        )
    if reason == "identified_no_intent":
        # A bare 4-digit FIRST message (app/nlu/pipeline.py's resolve_first_message_bare_last4)
        # resolved exactly one vehicle but no intent at all — deliberately doesn't guess what
        # the user wants to know, just confirms the vehicle and asks.
        return f"Found {plate_list} — what would you like to know about it? (e.g. location, speed, fuel level, trip history...)"
    if reason == "identified_no_intent_collision":
        # Same first-message case, but the digits matched more than one vehicle — nothing is
        # resolved yet, so this asks for both the vehicle and the intent in one turn rather
        # than two separate clarifying questions.
        return (
            f"More than one of your vehicles matches those last 4 digits: {plate_list}. "
            "Could you give me the full registration number, and let me know what you'd like to check?"
        )
    return (
        f"You have multiple vehicles: {plate_list}. Which one are you asking about? "
        "You can reply with the full registration number or just the last 4 digits."
    )


def clarifying_question(missing: str, ambiguous_vehicle_ref: dict | None = None) -> str:
    if missing == "vehicle_ref" and ambiguous_vehicle_ref:
        return _vehicle_list_question(ambiguous_vehicle_ref)
    return _TEMPLATES.get(missing, _DEFAULT)
