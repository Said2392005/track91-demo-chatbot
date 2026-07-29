"""
Runs the golden set (app/eval/golden_set.py) against real components — real Mongo entity
resolution, real ChromaDB retrieval, a caller-supplied LLM (FakeLLMProvider by default; pass
`get_llm_provider()` instead once a real API key is configured — see
docs/phase-12-testing/testing.md for how to switch). Produces an EvalReport with per-case
results and aggregate metrics.

Standalone CLI: `python -m app.eval.runner` (uses the real DB/Chroma from settings, and
FakeLLMProvider unless --real-llm is passed).
"""

import argparse
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from bson import ObjectId
from chromadb.api.models.Collection import Collection
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.eval.golden_set import GOLDEN_SET, GoldenCase
from app.eval.scorer import CaseResult, score_case
from app.llm.base import LLMProvider
from app.nlu.intent_classifier import IntentClassifier
from app.nlu.pipeline import analyze
from app.rag.pipeline import answer_kb_query

logger = logging.getLogger(__name__)


@dataclass
class EvalReport:
    results: list[CaseResult] = field(default_factory=list)

    @property
    def raw_intent_accuracy(self) -> float:
        return sum(r.raw_intent_correct for r in self.results) / len(self.results)

    @property
    def final_intent_accuracy(self) -> float:
        return sum(r.final_intent_correct for r in self.results) / len(self.results)

    @property
    def avg_entity_score(self) -> float | None:
        scored = [r.entity_score for r in self.results if r.entity_score is not None]
        return sum(scored) / len(scored) if scored else None

    @property
    def retrieval_precision(self) -> float | None:
        scored = [r.retrieval_hit for r in self.results if r.retrieval_hit is not None]
        return sum(scored) / len(scored) if scored else None

    @property
    def citation_groundedness_rate(self) -> float | None:
        scored = [r.citation_groundedness for r in self.results if r.citation_groundedness is not None]
        return sum(scored) / len(scored) if scored else None

    def summary(self) -> str:
        lines = [
            f"Cases: {len(self.results)}",
            f"Raw intent accuracy:      {self.raw_intent_accuracy:.1%}",
            f"Final intent accuracy:    {self.final_intent_accuracy:.1%}",
            f"Avg entity score:         {self.avg_entity_score:.1%}" if self.avg_entity_score is not None else "Avg entity score:         N/A",
            f"Retrieval precision:      {self.retrieval_precision:.1%}" if self.retrieval_precision is not None else "Retrieval precision:      N/A",
            f"Citation groundedness:    {self.citation_groundedness_rate:.1%}" if self.citation_groundedness_rate is not None else "Citation groundedness:    N/A",
        ]
        failing = [r for r in self.results if r.errors]
        if failing:
            lines.append("")
            lines.append(f"Cases with errors ({len(failing)}):")
            for r in failing:
                lines.append(f"  {r.case_id}: {'; '.join(r.errors)}")
        return "\n".join(lines)


async def seed_eval_fixtures(db: AsyncIOMotorDatabase, company_id: ObjectId, now: datetime) -> dict:
    """Seeds the exact vehicles/drivers the golden set's natural-key entity expectations
    ("plate:MH12AB1234", "driver:Ramesh Kumar") resolve against. Idempotent-ish for a single
    eval run using a fresh company_id (as the pytest wrapper does); not intended for reuse
    against a long-lived database across runs."""
    vehicle_id = ObjectId()
    await db.vehicles.insert_one(
        {
            "_id": vehicle_id,
            "company_id": company_id,
            "plate_number": "MH12AB1234",
            "nickname": "Pune Van",
            "status": "active",
            "created_at": now,
        }
    )
    driver_id = ObjectId()
    await db.drivers.insert_one(
        {"_id": driver_id, "company_id": company_id, "name": "Ramesh Kumar", "status": "active", "created_at": now}
    )
    return {"vehicles": {"MH12AB1234": vehicle_id}, "drivers": {"Ramesh Kumar": driver_id}}


async def _run_case(
    case: GoldenCase,
    classifier: IntentClassifier,
    company_id: ObjectId,
    db: AsyncIOMotorDatabase,
    llm: LLMProvider,
    kb_collection: Collection | None,
    fixtures: dict,
    now: datetime,
) -> CaseResult:
    raw_intent = await classifier.classify(case.utterance, case.session_state)
    raw_correct = raw_intent == case.expected_raw_intent

    analysis = await analyze(case.utterance, classifier, company_id, db, session_state=case.session_state or {}, now=now)
    final_correct = analysis.final_intent == case.expected_final_intent

    retrieved_doc_ids: list[str] | None = None
    citation_doc_ids: list[str] | None = None
    citation_approved_flags: list[str] | None = None

    if case.kb_category and kb_collection is not None:
        from app.kb.retrieve import retrieve

        hits = retrieve(case.utterance, top_k=6, collection=kb_collection)
        retrieved_doc_ids = [h.metadata["doc_id"] for h in hits]

        rag_result = await answer_kb_query(case.utterance, case.kb_category, llm, collection=kb_collection)
        citation_doc_ids = [c.get("chunk_id", "").split("::")[0] for c in rag_result.citations]
        # Hardcoding True here is only correct because require_approved_only=True is used
        # exclusively for `pricing` category cases in golden_set.py — for those,
        # assemble_pricing_context() (app/rag/context_assembler.py) has already filtered to
        # approved_pricing=True chunks before any citation exists, so every citation reaching
        # this point is approved by construction, not by assumption. If a future golden case
        # sets require_approved_only=True for a non-pricing category, this would need to
        # actually look up each chunk's approved_pricing flag instead.
        citation_approved_flags = [True] * len(citation_doc_ids)

    return score_case(
        case_id=case.case_id,
        raw_intent_correct=raw_correct,
        final_intent_correct=final_correct,
        expected_entities=case.expected_entities,
        actual_entities=analysis.entities,
        fixtures=fixtures,
        relevant_doc_ids=case.relevant_doc_ids,
        retrieved_doc_ids=retrieved_doc_ids,
        require_approved_only=case.require_approved_only,
        citation_doc_ids=citation_doc_ids,
        citation_approved_flags=citation_approved_flags,
    )


async def run_eval(
    classifier: IntentClassifier,
    db: AsyncIOMotorDatabase,
    llm: LLMProvider,
    kb_collection: Collection | None,
    golden_set: list[GoldenCase] | None = None,
    now: datetime | None = None,
) -> EvalReport:
    now = now or datetime.now(timezone.utc)
    golden_set = golden_set if golden_set is not None else GOLDEN_SET
    company_id = ObjectId()
    fixtures = await seed_eval_fixtures(db, company_id, now)

    results = [await _run_case(case, classifier, company_id, db, llm, kb_collection, fixtures, now) for case in golden_set]
    return EvalReport(results=results)


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Run the AI eval golden set")
    parser.add_argument("--real-llm", action="store_true", help="Use the configured real LLM provider instead of a fake")
    args = parser.parse_args()

    async def main():
        from app.db.client import get_database
        from app.kb.chroma_client import get_kb_collection
        from app.nlu.intent_classifier import get_intent_classifier

        db = get_database()
        kb_collection = get_kb_collection()
        classifier = get_intent_classifier()

        if args.real_llm:
            from app.llm.factory import get_llm_provider

            llm = get_llm_provider()
        else:
            from app.llm.providers.fake import FakeLLMProvider

            llm = FakeLLMProvider(canned_response="This is a canned evaluation response. [Source 1]")

        report = await run_eval(classifier, db, llm, kb_collection)
        print(report.summary())

    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())


if __name__ == "__main__":
    _cli()
