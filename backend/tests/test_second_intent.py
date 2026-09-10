"""Unit tests for the detector's mechanics — see test_second_intent_eval.py for whether it's
actually trustworthy on realistic input (measured 0% false-positive rate; NOT wired into the
main chat pipeline yet, per explicit instruction)."""

from app.nlu.second_intent import detect_second_intent


def test_no_second_signal_returns_none():
    assert detect_second_intent("Where is MH12AB1234?", "GET_VEHICLE_LOCATION") is None


def test_detects_a_real_second_intent():
    result = detect_second_intent("list drivers and vehicle location", "GET_DRIVER_ROSTER")
    assert result == "GET_VEHICLE_LOCATION"


def test_never_returns_the_primary_intent_itself():
    """GET_DRIVER_ROSTER's own score is high (it's the primary) — popped before ranking, so it
    can never come back as its own "second" intent even though it would otherwise be the max."""
    result = detect_second_intent("list all drivers", "GET_DRIVER_ROSTER")
    assert result != "GET_DRIVER_ROSTER"
    assert result is None  # nothing else scores on this single-intent utterance


def test_threshold_parameter_is_a_real_cutoff():
    """"list drivers and vehicle location" scores exactly 3 for GET_VEHICLE_LOCATION (measured,
    see second_intent_golden_set.py — was 2 before the all-intent trigger-coverage pass added a
    bare "location" TRIGGER_PHRASES entry, which now also matches inside "vehicle location" and
    adds its own word-count; re-measured then, not assumed) — a threshold at that score must
    include it, one above must exclude it. Proves the cutoff is a real boundary, not a no-op
    parameter."""
    utterance = "list drivers and vehicle location"
    assert detect_second_intent(utterance, "GET_DRIVER_ROSTER", threshold=3) == "GET_VEHICLE_LOCATION"
    assert detect_second_intent(utterance, "GET_DRIVER_ROSTER", threshold=4) is None


def test_negative_case_reused_from_rejected_splitter_eval():
    """"Ramesh and Suresh" — two drivers, one intent. Exactly the kind of case a naive detector
    could misfire on; must not."""
    result = detect_second_intent("Show trips for Ramesh and Suresh", "GET_TRIP_HISTORY")
    assert result is None
