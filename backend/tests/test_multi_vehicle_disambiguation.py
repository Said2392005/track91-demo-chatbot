"""
Multi-vehicle disambiguation — a user with more than one vehicle asking "where is my vehicle"
(no plate/nickname mentioned) is offered a list of their own plate numbers to pick from, instead
of a generic "which vehicle?" or (worse) an arbitrary guess. A reply of just the last 4 digits
of a plate is then resolved against that specific company's own vehicles — never another
company's, per this build's tenant-isolation rule (ADR 004) — and a collision (more than one of
the user's own vehicles sharing those last 4 digits) shows all matches rather than guessing or
asking for more digits (see conversation history / the recommendation this was built against).

Company-scoped, not per-user: this app has no per-user vehicle ownership concept anywhere in
the schema (checked before building this) — every user in a company already sees that company's
whole fleet (e.g. GET_VEHICLE_ROSTER). "The user's vehicles" here means "their company's
vehicles", consistent with how every other intent in this app already works.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from bson import ObjectId

from app.db.repositories.vehicle_repository import VehicleRepository
from app.nlu.entity_extractor import extract_entities, resolve_first_message_bare_last4
from app.nlu.intent_classifier import RuleBasedIntentClassifier
from app.nlu.pipeline import analyze
from app.router.clarification import clarifying_question
from app.router.router import route


async def _insert_vehicle(db, company_id, plate, now):
    vehicle_id = ObjectId()
    await db.vehicles.insert_one(
        {
            "_id": vehicle_id,
            "company_id": company_id,
            "plate_number": plate,
            "status": "active",
            "created_at": now,
        }
    )
    return vehicle_id


@pytest_asyncio.fixture(scope="module")
async def fleet(db):
    """A 5-vehicle company (mirroring the seed_data.py fixture), two of whose plates
    deliberately share the same last 4 digits (RJ14AB1234 / RJ14CD1234) so the collision case is
    reachable here without depending on running seed_data.py. Plus a second, single-vehicle
    company (the "exactly one vehicle" contrast case) and a third, unrelated company whose own
    vehicle happens to share the same last-4 digits — the tenant-isolation trap."""
    now = datetime.now(timezone.utc)
    company_id = ObjectId()
    plates = {
        "ab": ("RJ14AB1234", await _insert_vehicle(db, company_id, "RJ14AB1234", now)),
        "cd": ("RJ14CD1234", await _insert_vehicle(db, company_id, "RJ14CD1234", now)),
        "ef": ("RJ14EF5678", await _insert_vehicle(db, company_id, "RJ14EF5678", now)),
        "gh": ("RJ14GH9012", await _insert_vehicle(db, company_id, "RJ14GH9012", now)),
        "ij": ("RJ14IJ3456", await _insert_vehicle(db, company_id, "RJ14IJ3456", now)),
    }

    single_vehicle_company_id = ObjectId()
    solo_vehicle_id = await _insert_vehicle(db, single_vehicle_company_id, "MH12AB1234", now)

    other_company_id = ObjectId()
    # Same last 4 digits as the fleet's own collision pair, but a different company entirely —
    # must never appear in `fleet`'s results, no matter which resolution path is exercised.
    other_company_vehicle_id = await _insert_vehicle(db, other_company_id, "KA05ZZ1234", now)

    return {
        "company_id": company_id,
        "plates": plates,
        "single_vehicle_company_id": single_vehicle_company_id,
        "solo_vehicle_id": solo_vehicle_id,
        "other_company_id": other_company_id,
        "other_company_vehicle_id": other_company_vehicle_id,
    }


# --- Entity extraction level ---


async def test_no_vehicle_mentioned_with_multiple_vehicles_lists_all_plates(db, fleet):
    result = await extract_entities("where is my vehicle", "GET_VEHICLE_LOCATION", fleet["company_id"], db)

    assert "vehicle_id" not in result.entities
    assert "vehicle_ref" not in result.unresolved_required
    assert "vehicle_ref" in result.ambiguous
    assert result.ambiguous["vehicle_ref"]["reason"] == "unspecified"
    listed_plates = {v["plate_number"] for v in result.ambiguous["vehicle_ref"]["candidates"]}
    assert listed_plates == {plate for plate, _ in fleet["plates"].values()}


async def test_no_vehicle_mentioned_with_exactly_one_vehicle_stays_a_plain_question(db, fleet):
    """The contrast case: a single-vehicle company gets the existing generic "which vehicle?"
    behavior, not a pointless one-item list — this feature only changes behavior once there's
    an actual choice to make."""
    result = await extract_entities(
        "what's my vehicle's status", "GET_VEHICLE_HEALTH", fleet["single_vehicle_company_id"], db
    )
    assert "vehicle_id" not in result.entities
    assert "vehicle_ref" not in result.ambiguous
    assert "vehicle_ref" in result.unresolved_required


async def test_optional_vehicle_ref_with_nothing_mentioned_is_not_treated_as_ambiguous(db, fleet):
    """GET_TRIP_SUMMARY's vehicle_ref is optional — nothing mentioned legitimately means "answer
    for the whole fleet", not "ask which vehicle". Must not trigger the new listing behavior."""
    result = await extract_entities("how many km did we cover last week", "GET_TRIP_SUMMARY", fleet["company_id"], db)
    assert "vehicle_ref" not in result.ambiguous


async def test_last4_digits_resolve_to_the_correct_vehicle_on_resume(db, fleet):
    result = await extract_entities(
        "5678",
        "GET_VEHICLE_LOCATION",
        fleet["company_id"],
        db,
        resolve_vehicle_by_last4=True,
    )
    _, expected_id = fleet["plates"]["ef"]
    assert result.entities["vehicle_id"] == expected_id


async def test_last4_digits_are_not_matched_outside_the_resume_path(db, fleet):
    """Safety rail: without resolve_vehicle_by_last4=True (the default), a bare 4-digit reply
    must NOT resolve to a vehicle — this is deliberately gated to the pending-clarification-
    resume path only (app/nlu/pipeline.py), never general free-text extraction, so an unrelated
    4-digit number in an ordinary message can't accidentally match a plate."""
    result = await extract_entities("5678", "GET_VEHICLE_LOCATION", fleet["company_id"], db)
    assert "vehicle_id" not in result.entities


async def test_last4_digit_collision_lists_only_the_colliding_vehicles(db, fleet):
    result = await extract_entities(
        "1234",
        "GET_VEHICLE_LOCATION",
        fleet["company_id"],
        db,
        resolve_vehicle_by_last4=True,
    )
    assert "vehicle_id" not in result.entities
    assert "vehicle_ref" in result.ambiguous
    assert result.ambiguous["vehicle_ref"]["reason"] == "last4_collision"
    listed_plates = {v["plate_number"] for v in result.ambiguous["vehicle_ref"]["candidates"]}
    # Exactly the two colliding plates — not all 5, and not the unrelated ones.
    assert listed_plates == {"RJ14AB1234", "RJ14CD1234"}


async def test_last4_match_never_crosses_company_boundary(db, fleet):
    """The tenant-isolation trap: `other_company_id` has its own vehicle ending in 1234
    (KA05ZZ1234) — resolving "1234" against `fleet`'s own company_id must never see it, whether
    that produces a collision (as it does here, within fleet's own two vehicles) or a clean
    single match."""
    repo = VehicleRepository(db)
    matches = await repo.find_by_plate_last4(fleet["company_id"], "1234")
    matched_plates = {v["plate_number"] for v in matches}
    assert "KA05ZZ1234" not in matched_plates
    assert matched_plates == {"RJ14AB1234", "RJ14CD1234"}

    other_company_matches = await repo.find_by_plate_last4(fleet["other_company_id"], "1234")
    assert {v["plate_number"] for v in other_company_matches} == {"KA05ZZ1234"}


# --- Router / clarifying-question level ---


def test_clarifying_question_lists_plates_for_the_unspecified_case():
    ambiguous = {"reason": "unspecified", "candidates": [{"plate_number": "RJ14AB1234"}, {"plate_number": "RJ14EF5678"}]}
    question = clarifying_question("vehicle_ref", ambiguous)
    assert "RJ14AB1234" in question
    assert "RJ14EF5678" in question
    assert "last 4 digits" in question.lower()  # tells the user the shortcut is available


def test_clarifying_question_for_a_collision_does_not_suggest_last4_again():
    ambiguous = {"reason": "last4_collision", "candidates": [{"plate_number": "RJ14AB1234"}, {"plate_number": "RJ14CD1234"}]}
    question = clarifying_question("vehicle_ref", ambiguous)
    assert "RJ14AB1234" in question
    assert "RJ14CD1234" in question
    # Suggesting "reply with ... the last 4 digits" again (the unspecified case's affordance)
    # would be nonsensical here — that's exactly what just collided. Mentioning "last 4 digits"
    # descriptively (to explain why these two matched) is fine; re-offering it as the way to
    # answer is not.
    assert "or just the last 4 digits" not in question.lower()


def test_route_produces_the_dynamic_vehicle_list_question():
    ambiguous = {"vehicle_ref": {"reason": "unspecified", "candidates": [{"plate_number": "RJ14AB1234"}]}}
    decision = route("GET_VEHICLE_LOCATION", {}, None, ambiguous)
    assert decision.outcome == "CLARIFICATION_NEEDED"
    assert decision.missing_entity == "vehicle_ref"
    assert "RJ14AB1234" in decision.clarifying_question


def test_route_without_ambiguous_data_falls_back_to_the_generic_question():
    """Backward compatible: callers that don't pass `ambiguous` (or a company with only one
    vehicle, which never populates it) still get the original fixed template."""
    decision = route("GET_VEHICLE_LOCATION", {}, None)
    assert decision.outcome == "CLARIFICATION_NEEDED"
    assert decision.clarifying_question == "Which vehicle are you asking about? You can give me its registration number."


# --- Full pipeline: list -> reply with last 4 digits -> resolved ---


async def test_full_resume_flow_from_listing_to_last4_resolution(db, fleet):
    classifier = RuleBasedIntentClassifier()

    turn1 = await analyze("where is my vehicle", classifier, fleet["company_id"], db, session_state={})
    assert turn1.final_intent == "CLARIFICATION_NEEDED"
    assert turn1.ambiguous["vehicle_ref"]["reason"] == "unspecified"

    pending = {"intent": "GET_VEHICLE_LOCATION", "missing": "vehicle_ref"}
    turn2 = await analyze("5678", classifier, fleet["company_id"], db, session_state={"pending_clarification": pending})
    assert turn2.raw_intent == "GET_VEHICLE_LOCATION"
    assert turn2.final_intent == "GET_VEHICLE_LOCATION"
    _, expected_id = fleet["plates"]["ef"]
    assert turn2.entities["vehicle_id"] == expected_id


async def test_full_resume_flow_hits_collision_then_resolves_with_full_plate(db, fleet):
    classifier = RuleBasedIntentClassifier()
    pending = {"intent": "GET_VEHICLE_LOCATION", "missing": "vehicle_ref"}

    turn2 = await analyze("1234", classifier, fleet["company_id"], db, session_state={"pending_clarification": pending})
    assert turn2.final_intent == "CLARIFICATION_NEEDED"
    assert turn2.ambiguous["vehicle_ref"]["reason"] == "last4_collision"

    # The user picks by replying with the full plate this time.
    pending_after_collision = {"intent": "GET_VEHICLE_LOCATION", "missing": "vehicle_ref"}
    turn3 = await analyze(
        "RJ14CD1234", classifier, fleet["company_id"], db, session_state={"pending_clarification": pending_after_collision}
    )
    assert turn3.final_intent == "GET_VEHICLE_LOCATION"
    _, expected_id = fleet["plates"]["cd"]
    assert turn3.entities["vehicle_id"] == expected_id


async def test_resume_flow_never_resolves_another_companys_vehicle_via_last4(db, fleet):
    """End-to-end version of the tenant-isolation trap: a reply of "1234" while resuming a
    clarification for `other_company_id` (which has exactly one vehicle ending in 1234) must
    resolve to THAT company's own vehicle, never leak into or be confused with `fleet`'s two
    colliding vehicles that share the same last 4 digits."""
    classifier = RuleBasedIntentClassifier()
    pending = {"intent": "GET_VEHICLE_LOCATION", "missing": "vehicle_ref"}

    result = await analyze(
        "1234", classifier, fleet["other_company_id"], db, session_state={"pending_clarification": pending}
    )
    assert result.final_intent == "GET_VEHICLE_LOCATION"
    assert result.entities["vehicle_id"] == fleet["other_company_vehicle_id"]


# --- First message, bare digits, no pending clarification at all ---
#
# Different from everything above: there's no known intent yet at all (not "resume a vehicle_ref
# clarification for GET_VEHICLE_LOCATION" — we don't know it's GET_VEHICLE_LOCATION, or any
# other specific intent). Deliberately does NOT default to GET_VEHICLE_LOCATION or any other
# intent — a bare number gives no signal narrowing down which of ~10 vehicle-specific intents is
# meant, and a wrong-but-confident answer is worse than asking. Resolves the vehicle (or the
# collision) and asks what the user wants to know, setting the resolved vehicle as the active
# entity so the next turn — any real phrasing at all, via the pre-existing pronoun/memory path,
# no new mechanism needed for it — resolves correctly.


async def test_resolve_first_message_bare_last4_single_match(db, fleet):
    resolution = await resolve_first_message_bare_last4("5678", fleet["company_id"], db)
    _, expected_id = fleet["plates"]["ef"]
    assert resolution.vehicle["_id"] == expected_id
    assert resolution.ambiguous is None


async def test_resolve_first_message_bare_last4_collision(db, fleet):
    resolution = await resolve_first_message_bare_last4("1234", fleet["company_id"], db)
    assert resolution.vehicle is None
    assert resolution.ambiguous["reason"] == "identified_no_intent_collision"
    assert {v["plate_number"] for v in resolution.ambiguous["candidates"]} == {"RJ14AB1234", "RJ14CD1234"}


async def test_resolve_first_message_bare_last4_no_match(db, fleet):
    resolution = await resolve_first_message_bare_last4("0000", fleet["company_id"], db)
    assert resolution.vehicle is None
    assert resolution.ambiguous is None


@pytest.mark.parametrize(
    "utterance",
    [
        "call 1234 for support",
        "meet me at 1234 Main Street",
        "my order number is 5678",
        "5678 and 1234",
    ],
)
async def test_resolve_first_message_bare_last4_requires_the_whole_message_to_be_just_digits(db, fleet, utterance):
    """A message that merely *contains* 4 digits somewhere must NOT trigger a vehicle lookup —
    only a message that IS just the 4 digits. Stricter than the clarification-resume path's
    _extract_bare_last4 on purpose: there's no established context here confirming the user is
    specifically answering a plate question."""
    resolution = await resolve_first_message_bare_last4(utterance, fleet["company_id"], db)
    assert resolution.vehicle is None
    assert resolution.ambiguous is None


async def test_full_pipeline_first_message_bare_digits_resolves_vehicle_asks_intent(db, fleet):
    classifier = RuleBasedIntentClassifier()

    result = await analyze("5678", classifier, fleet["company_id"], db, session_state={})

    assert result.raw_intent == "OUT_OF_SCOPE"
    assert result.final_intent == "CLARIFICATION_NEEDED"
    _, expected_id = fleet["plates"]["ef"]
    assert result.entities["vehicle_id"] == expected_id
    assert result.ambiguous["vehicle_ref"]["reason"] == "identified_no_intent"


async def test_full_pipeline_first_message_bare_digits_collision_asks_for_both(db, fleet):
    classifier = RuleBasedIntentClassifier()

    result = await analyze("1234", classifier, fleet["company_id"], db, session_state={})

    assert result.raw_intent == "OUT_OF_SCOPE"
    assert result.final_intent == "CLARIFICATION_NEEDED"
    assert "vehicle_id" not in result.entities
    assert result.ambiguous["vehicle_ref"]["reason"] == "identified_no_intent_collision"


async def test_full_pipeline_first_message_no_match_stays_out_of_scope(db, fleet):
    """No real vehicle matches — must fall through to the normal, unchanged OUT_OF_SCOPE
    behavior, not a false "found a vehicle" clarification."""
    classifier = RuleBasedIntentClassifier()

    result = await analyze("0000", classifier, fleet["company_id"], db, session_state={})

    assert result.raw_intent == "OUT_OF_SCOPE"
    assert result.final_intent == "OUT_OF_SCOPE"
    assert result.entities == {}
    assert result.ambiguous == {}


async def test_clarifying_question_for_first_message_single_match_asks_what_not_which():
    ambiguous = {"reason": "identified_no_intent", "candidates": [{"plate_number": "RJ14EF5678"}]}
    question = clarifying_question("vehicle_ref", ambiguous)
    assert "RJ14EF5678" in question
    assert "what would you like to know" in question.lower()


async def test_clarifying_question_for_first_message_collision_asks_for_both_plate_and_intent():
    ambiguous = {
        "reason": "identified_no_intent_collision",
        "candidates": [{"plate_number": "RJ14AB1234"}, {"plate_number": "RJ14CD1234"}],
    }
    question = clarifying_question("vehicle_ref", ambiguous)
    assert "RJ14AB1234" in question
    assert "RJ14CD1234" in question
    assert "full registration number" in question.lower()
    assert "what you'd like to check" in question.lower()


async def test_route_produces_clarification_for_out_of_scope_with_resolved_vehicle():
    """route()'s NONE-subsystem branch must only special-case OUT_OF_SCOPE when it's carrying
    this specific resolved-vehicle signal — every other OUT_OF_SCOPE/meta-intent call must be
    completely unaffected."""
    ambiguous = {"vehicle_ref": {"reason": "identified_no_intent", "candidates": [{"plate_number": "RJ14EF5678"}]}}
    decision = route("OUT_OF_SCOPE", {}, None, ambiguous)
    assert decision.outcome == "CLARIFICATION_NEEDED"
    assert decision.missing_entity == "vehicle_ref"
    assert "RJ14EF5678" in decision.clarifying_question


async def test_route_ordinary_out_of_scope_is_unaffected():
    decision = route("OUT_OF_SCOPE", {}, None)
    assert decision.outcome == "NO_TOOL"
    assert decision.clarifying_question is None


async def test_first_message_bare_digits_never_resolves_another_companys_vehicle(db, fleet):
    """The tenant-isolation trap, first-message version: `other_company_id` has its own vehicle
    ending in 1234 (KA05ZZ1234, no collision within its own company) — resolving a first
    message of "1234" against `fleet`'s own company_id must hit the two-way collision within
    fleet's own vehicles, never leak in or resolve to the other company's vehicle."""
    resolution = await resolve_first_message_bare_last4("1234", fleet["company_id"], db)
    assert resolution.vehicle is None
    matched_plates = {v["plate_number"] for v in resolution.ambiguous["candidates"]}
    assert "KA05ZZ1234" not in matched_plates
    assert matched_plates == {"RJ14AB1234", "RJ14CD1234"}

    other_resolution = await resolve_first_message_bare_last4("1234", fleet["other_company_id"], db)
    assert other_resolution.vehicle["_id"] == fleet["other_company_vehicle_id"]
    assert other_resolution.ambiguous is None


async def test_second_turn_after_first_message_resolution_uses_active_entity_via_pronoun(db, fleet):
    """The actual payoff of setting the active entity on turn 1: turn 2 doesn't need any new
    digit-matching at all — a completely ordinary phrasing ("what's its fuel level") resolves
    the vehicle through the pre-existing pronoun/active-entity mechanism (app/nlu/coreference.py
    + app/memory/active_entity_tracker.py), the same as if the vehicle had been mentioned by
    plate. This test drives that memory write directly (mirroring what
    app/agent/nodes.py's memory_update_node does with turn 1's AnalysisResult.entities) rather
    than the full graph, since this file tests app/nlu/pipeline.py in isolation elsewhere too."""
    from app.db.repositories.session_repository import SessionRepository
    from app.memory.active_entity_tracker import set_active_entity

    classifier = RuleBasedIntentClassifier()
    now = datetime.now(timezone.utc)
    session_repo = SessionRepository(db)
    session = await session_repo.create(fleet["company_id"], ObjectId(), now)

    turn1 = await analyze("5678", classifier, fleet["company_id"], db, session_state={})
    _, expected_id = fleet["plates"]["ef"]
    assert turn1.entities["vehicle_id"] == expected_id
    await set_active_entity(session_repo, fleet["company_id"], session["_id"], "vehicle", expected_id, now)

    active_entities = {"vehicle_id": expected_id}
    turn2 = await analyze(
        "what's its fuel level?", classifier, fleet["company_id"], db, session_state={"active_entities": active_entities}
    )
    assert turn2.raw_intent == "GET_VEHICLE_FUEL_LEVEL"
    assert turn2.final_intent == "GET_VEHICLE_FUEL_LEVEL"
    assert turn2.entities["vehicle_id"] == expected_id
