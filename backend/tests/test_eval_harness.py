"""
AI eval golden-set harness test — Phase 12 requirement: 40-60 Q&A pairs across every intent,
scored on intent-classification accuracy, entity-extraction accuracy, retrieval precision, and
answer faithfulness (via a citation-groundedness proxy — see app/eval/scorer.py's docstring for
why a proxy, not true hallucination detection, given FakeLLMProvider is used per current
project decision; docs/phase-12-testing/testing.md explains how to switch to a real LLM).

Thresholds are set from real measured numbers (documented in testing.md's iteration history),
not picked to make the test pass: after two real fixes this phase (a content-safety gap where
unapproved pricing content could leak into unrelated answers, and three classifier trigger
gaps), the actual run is 100% intent accuracy, 100% entity accuracy, 100% retrieval precision,
81.8% citation groundedness. The remaining groundedness gap is the same small-KB retrieval
imprecision Phase 7 already measured and documented (~87-94% precision@k on this 28-chunk KB) —
not chased further here for the same reason it wasn't in Phase 7.
"""

import chromadb
import pytest

from app.eval.golden_set import GOLDEN_SET
from app.eval.runner import EvalReport, run_eval
from app.kb.chunker import load_and_chunk_source_dir
from app.kb.ingest import ingest_chunks
from app.llm.providers.fake import FakeLLMProvider
from app.nlu.intent_classifier import RuleBasedIntentClassifier
from tests.test_kb_ingestion import KB_SOURCE_DIR

MIN_RAW_INTENT_ACCURACY = 0.95
MIN_FINAL_INTENT_ACCURACY = 0.95
MIN_ENTITY_SCORE = 0.95
MIN_RETRIEVAL_PRECISION = 0.90
MIN_CITATION_GROUNDEDNESS = 0.75


@pytest.fixture(scope="module")
def kb_collection():
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection("kb_chunks_eval_harness_test")
    ingest_chunks(load_and_chunk_source_dir(KB_SOURCE_DIR), collection=collection)
    return collection


@pytest.fixture(scope="module")
async def report(db, kb_collection) -> EvalReport:
    llm = FakeLLMProvider(canned_response="This is a canned evaluation response. [Source 1]")
    return await run_eval(RuleBasedIntentClassifier(), db, llm, kb_collection, golden_set=GOLDEN_SET)


def test_golden_set_has_40_to_60_cases_covering_every_intent():
    from app.core.taxonomy import ALL_INTENTS

    assert 40 <= len(GOLDEN_SET) <= 60
    covered = {c.expected_raw_intent for c in GOLDEN_SET} | {c.expected_final_intent for c in GOLDEN_SET}
    assert covered == set(ALL_INTENTS), f"missing intents: {set(ALL_INTENTS) - covered}"


async def test_raw_intent_accuracy(report):
    assert report.raw_intent_accuracy >= MIN_RAW_INTENT_ACCURACY, report.summary()


async def test_final_intent_accuracy(report):
    assert report.final_intent_accuracy >= MIN_FINAL_INTENT_ACCURACY, report.summary()


async def test_entity_extraction_accuracy(report):
    assert report.avg_entity_score >= MIN_ENTITY_SCORE, report.summary()


async def test_retrieval_precision(report):
    assert report.retrieval_precision >= MIN_RETRIEVAL_PRECISION, report.summary()


async def test_citation_groundedness_as_faithfulness_proxy(report):
    assert report.citation_groundedness_rate >= MIN_CITATION_GROUNDEDNESS, report.summary()


async def test_pricing_gate_holds_within_the_eval_run(report):
    """The one case explicitly designed to test the gate under ambiguity (Phase 7/9's finding:
    the unapproved draft chunk ranks #1 by raw distance) must still show grounded, approved-only
    citations when scored through this harness specifically."""
    pricing_case = next(r for r in report.results if r.case_id == "pricing_ambiguous")
    assert pricing_case.citation_groundedness is True
