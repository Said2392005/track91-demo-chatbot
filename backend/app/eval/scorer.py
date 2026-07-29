"""
Scoring for a single golden-set case. Kept separate from runner.py (which does the I/O —
classification, entity extraction, retrieval) so the scoring logic itself is pure and unit-
testable without a database or LLM.
"""

from dataclasses import dataclass, field


@dataclass
class CaseResult:
    case_id: str
    raw_intent_correct: bool
    final_intent_correct: bool
    entity_score: float | None  # fraction of expected entities matched; None if none expected
    retrieval_hit: bool | None  # at least one relevant doc in top-k; None if not a scored RAG case
    citation_groundedness: bool | None  # every citation traces to an allowed doc; None if N/A
    errors: list[str] = field(default_factory=list)


def resolve_expected_entity_value(value: str, fixtures: dict):
    """"PRESENT" -> sentinel meaning "just check non-empty"; "plate:X"/"driver:X" -> resolved
    ObjectId from seeded fixtures; anything else -> literal expected value."""
    if value == "PRESENT":
        return "PRESENT"
    if value.startswith("plate:"):
        return fixtures["vehicles"][value.removeprefix("plate:")]
    if value.startswith("driver:"):
        return fixtures["drivers"][value.removeprefix("driver:")]
    return value


def score_entities(expected_entities: dict[str, str], actual_entities: dict, fixtures: dict) -> tuple[float | None, list[str]]:
    if not expected_entities:
        return None, []

    errors = []
    correct = 0
    for key, raw_expected in expected_entities.items():
        expected = resolve_expected_entity_value(raw_expected, fixtures)
        actual = actual_entities.get(key)
        if expected == "PRESENT":
            ok = actual is not None and actual != ""
        else:
            ok = actual == expected
        if ok:
            correct += 1
        else:
            errors.append(f"entity {key!r}: expected {expected!r}, got {actual!r}")

    return correct / len(expected_entities), errors


def score_retrieval(relevant_doc_ids: list[str], retrieved_doc_ids: list[str]) -> bool | None:
    if not relevant_doc_ids:
        return None
    return any(doc_id in relevant_doc_ids for doc_id in retrieved_doc_ids)


def score_citation_groundedness(
    relevant_doc_ids: list[str], require_approved_only: bool, citation_doc_ids: list[str], citation_approved_flags: list[bool]
) -> bool | None:
    """A faithfulness *proxy*: with a fake/canned LLM, we can't measure whether generated prose
    hallucinates, but we CAN measure whether the context it was given is grounded — every
    citation traces to a doc this case considers relevant, and (for PRICING cases) every cited
    chunk is actually approved. This is what's actually under this system's control; true
    hallucination detection needs a real LLM's output, which this build doesn't have configured
    (see docs/phase-12-testing/testing.md)."""
    if not relevant_doc_ids:
        return None
    if not citation_doc_ids:
        return False
    if require_approved_only and not all(citation_approved_flags):
        return False
    return all(doc_id in relevant_doc_ids for doc_id in citation_doc_ids)


def score_case(
    case_id: str,
    raw_intent_correct: bool,
    final_intent_correct: bool,
    expected_entities: dict[str, str],
    actual_entities: dict,
    fixtures: dict,
    relevant_doc_ids: list[str],
    retrieved_doc_ids: list[str] | None,
    require_approved_only: bool,
    citation_doc_ids: list[str] | None,
    citation_approved_flags: list[bool] | None,
) -> CaseResult:
    entity_score, entity_errors = score_entities(expected_entities, actual_entities, fixtures)
    retrieval_hit = score_retrieval(relevant_doc_ids, retrieved_doc_ids or [])
    groundedness = score_citation_groundedness(
        relevant_doc_ids, require_approved_only, citation_doc_ids or [], citation_approved_flags or []
    )

    errors = list(entity_errors)
    if not raw_intent_correct:
        errors.append("raw_intent mismatch")
    if not final_intent_correct:
        errors.append("final_intent mismatch")
    if retrieval_hit is False:
        errors.append("no relevant doc retrieved in top-k")
    if groundedness is False:
        errors.append("citation(s) not grounded in an allowed/approved doc")

    return CaseResult(
        case_id=case_id,
        raw_intent_correct=raw_intent_correct,
        final_intent_correct=final_intent_correct,
        entity_score=entity_score,
        retrieval_hit=retrieval_hit,
        citation_groundedness=groundedness,
        errors=errors,
    )
