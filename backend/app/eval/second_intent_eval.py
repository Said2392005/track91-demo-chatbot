"""
Runs app/eval/second_intent_golden_set.py against app.nlu.second_intent.detect_second_intent()
and reports:

- false_positive_rate: negative cases (single-intent utterances) where a second intent was
  wrongly detected. The dangerous direction — same reason app/eval/splitter_eval.py measures it
  for the rejected conjunction-splitter.
- true_positive_rate: positive cases (real compound requests) where the RIGHT second intent was
  detected. A case that detects *some* second intent but the wrong one still counts as a miss,
  not a partial credit — see SecondIntentCaseResult.correct.

No DB/LLM/network involved — detect_second_intent() is a pure function over
score_all_intents(), so this eval is synchronous and instant.

Standalone CLI: `python -m app.eval.second_intent_eval`
"""

from dataclasses import dataclass

from app.eval.second_intent_golden_set import SECOND_INTENT_GOLDEN_SET, SecondIntentCase
from app.nlu.second_intent import detect_second_intent


@dataclass
class SecondIntentCaseResult:
    case_id: str
    utterance: str
    expect_second_intent: bool
    expected_second_intent: str | None
    detected: str | None

    @property
    def correct(self) -> bool:
        if not self.expect_second_intent:
            return self.detected is None
        return self.detected == self.expected_second_intent


@dataclass
class SecondIntentEvalReport:
    results: list[SecondIntentCaseResult]

    @property
    def negatives(self) -> list[SecondIntentCaseResult]:
        return [r for r in self.results if not r.expect_second_intent]

    @property
    def positives(self) -> list[SecondIntentCaseResult]:
        return [r for r in self.results if r.expect_second_intent]

    @property
    def false_positives(self) -> list[SecondIntentCaseResult]:
        return [r for r in self.negatives if r.detected is not None]

    @property
    def false_positive_rate(self) -> float:
        return len(self.false_positives) / len(self.negatives) if self.negatives else 0.0

    @property
    def true_positive_rate(self) -> float:
        hits = [r for r in self.positives if r.correct]
        return len(hits) / len(self.positives) if self.positives else 0.0

    def summary(self) -> str:
        lines = [
            f"Cases: {len(self.results)} ({len(self.negatives)} negative, {len(self.positives)} positive)",
            f"False-positive rate (singles wrongly flagged as compound): {self.false_positive_rate:.1%} "
            f"({len(self.false_positives)}/{len(self.negatives)})",
            f"True-positive rate (real pairs correctly detected):        {self.true_positive_rate:.1%} "
            f"({sum(r.correct for r in self.positives)}/{len(self.positives)})",
        ]
        if self.false_positives:
            lines.append("")
            lines.append("False positives:")
            for r in self.false_positives:
                lines.append(f"  [{r.case_id}] {r.utterance!r} -> wrongly detected {r.detected}")
        misses = [r for r in self.positives if not r.correct]
        if misses:
            lines.append("")
            lines.append("Missed or wrong positives:")
            for r in misses:
                lines.append(f"  [{r.case_id}] {r.utterance!r} -> expected {r.expected_second_intent}, got {r.detected}")
        return "\n".join(lines)


def _run_case(case: SecondIntentCase) -> SecondIntentCaseResult:
    detected = detect_second_intent(case.utterance, case.primary_intent)
    return SecondIntentCaseResult(
        case_id=case.case_id,
        utterance=case.utterance,
        expect_second_intent=case.expect_second_intent,
        expected_second_intent=case.expected_second_intent,
        detected=detected,
    )


def run_second_intent_eval(golden_set: list[SecondIntentCase] | None = None) -> SecondIntentEvalReport:
    golden_set = golden_set if golden_set is not None else SECOND_INTENT_GOLDEN_SET
    return SecondIntentEvalReport(results=[_run_case(case) for case in golden_set])


if __name__ == "__main__":
    print(run_second_intent_eval().summary())
