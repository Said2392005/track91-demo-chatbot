from app.nlu.coreference import contains_pronoun_reference, filter_active_entities_by_mentioned_type, resolve_active_entity


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


def test_filter_drops_vehicle_when_utterance_asks_about_a_driver():
    """Regression: found via live testing. "where is my driver" (in a session with an active
    vehicle) must not let that vehicle silently answer — the utterance explicitly names a
    different entity type."""
    active = {"vehicle_id": "veh_123"}
    assert filter_active_entities_by_mentioned_type("where is my driver", active) == {}


def test_filter_keeps_matching_type():
    active = {"driver_id": "drv_456"}
    assert filter_active_entities_by_mentioned_type("how is my driver doing", active) == {"driver_id": "drv_456"}


def test_filter_keeps_everything_when_utterance_names_no_entity_type():
    """"what's its speed" — a pronoun reference with no entity-type noun at all, the exact
    shape router.py's memory-fill exists for — must be unaffected."""
    active = {"vehicle_id": "veh_123", "driver_id": "drv_456"}
    assert filter_active_entities_by_mentioned_type("what's its speed?", active) == active


def test_filter_keeps_vehicle_when_utterance_names_vehicle_type():
    """"where is my vehicle" does name a type ("vehicle") — it's kept because it MATCHES what's
    active, not because nothing was mentioned. Distinct from the no-mention case above: an
    utterance naming the SAME type as what's active must still resolve via memory."""
    active = {"vehicle_id": "veh_123", "driver_id": "drv_456"}
    assert filter_active_entities_by_mentioned_type("where is my vehicle", active) == {"vehicle_id": "veh_123"}


def test_filter_only_narrows_never_expands():
    """Naming a type with nothing active for it must not invent an entry."""
    assert filter_active_entities_by_mentioned_type("where is my driver", {}) == {}


def test_filter_keeps_multiple_types_when_multiple_are_mentioned():
    active = {"vehicle_id": "veh_123", "driver_id": "drv_456", "geofence_id": "geo_789"}
    result = filter_active_entities_by_mentioned_type("which driver is assigned to which vehicle", active)
    assert result == {"vehicle_id": "veh_123", "driver_id": "drv_456"}
