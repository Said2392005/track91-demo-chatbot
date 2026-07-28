from app.nlu.coreference import contains_pronoun_reference, resolve_active_entity


def test_detects_common_pronoun_forms():
    for text in ["what's its speed?", "is that one moving?", "where are they now?", "track this one"]:
        assert contains_pronoun_reference(text), text


def test_does_not_falsely_flag_plain_text():
    assert not contains_pronoun_reference("where is MH12AB1234")


def test_resolve_active_entity_returns_stored_id():
    active = {"vehicle_id": "veh_123", "driver_id": "drv_456"}
    assert resolve_active_entity("vehicle", active) == "veh_123"
    assert resolve_active_entity("driver", active) == "drv_456"


def test_resolve_active_entity_missing_type_returns_none():
    assert resolve_active_entity("geofence", {"vehicle_id": "veh_123"}) is None


def test_resolve_active_entity_no_state_returns_none():
    assert resolve_active_entity("vehicle", None) is None
    assert resolve_active_entity("vehicle", {}) is None
