"""
Runs app/eval/splitter_golden_set.py against app.nlu.message_splitter.split_conjunctions() and
reports two separate rates:

- false_split_rate: negative cases (should NOT split) that got split anyway. This is the
  dangerous direction — it silently breaks a working single-intent question — and is the number
  this feature's rollout decision hinges on.
- false_negative_rate: positive cases (SHOULD split) that didn't. Undesirable but much safer —
  worst case, a compound request degrades to being answered as if only its first clause was
  asked, which is roughly today's (pre-splitter) behavior anyway.

No DB/LLM/network involved — split_conjunctions() is a pure function, so this eval is
synchronous and instant, unlike app/eval/runner.py's full-pipeline eval.

Standalone CLI: `python -m app.eval.splitter_eval`
"""

from dataclasses import dataclass

from app.eval.splitter_golden_set import SPLITTER_GOLDEN_SET, SplitterCase
from app.nlu.message_splitter import split_conjunctions


@dataclass
class SplitterCaseResult:
    case_id: str
    utterance: str
    should_split: bool
    actual_split: bool
    fragments: list[str]

    @property
    def correct(self) -> bool:
        return self.actual_split == self.should_split


@dataclass
class SplitterEvalReport:
    results: list[SplitterCaseResult]

    @property
    def false_splits(self) -> list[SplitterCaseResult]:
        return [r for r in self.results if not r.should_split and r.actual_split]

    @property
    def false_negatives(self) -> list[SplitterCaseResult]:
        return [r for r in self.results if r.should_split and not r.actual_split]

    @property
    def negatives(self) -> list[SplitterCaseResult]:
        return [r for r in self.results if not r.should_split]

    @property
    def positives(self) -> list[SplitterCaseResult]:
        return [r for r in self.results if r.should_split]

    @property
    def false_split_rate(self) -> float:
        return len(self.false_splits) / len(self.negatives) if self.negatives else 0.0

    @property
    def false_negative_rate(self) -> float:
        return len(self.false_negatives) / len(self.positives) if self.positives else 0.0

    def summary(self) -> str:
        lines = [
            f"Cases: {len(self.results)} ({len(self.negatives)} negative, {len(self.positives)} positive)",
            f"False-split rate (working questions wrongly split): {self.false_split_rate:.1%} "
            f"({len(self.false_splits)}/{len(self.negatives)})",
            f"False-negative rate (compound requests not split):  {self.false_negative_rate:.1%} "
            f"({len(self.false_negatives)}/{len(self.positives)})",
        ]
        if self.false_splits:
            lines.append("")
            lines.append("False splits:")
            for r in self.false_splits:
                lines.append(f"  [{r.case_id}] {r.utterance!r} -> {r.fragments}")
        if self.false_negatives:
            lines.append("")
            lines.append("False negatives (not split):")
            for r in self.false_negatives:
                lines.append(f"  [{r.case_id}] {r.utterance!r}")
        return "\n".join(lines)


def _run_case(case: SplitterCase) -> SplitterCaseResult:
    fragments = split_conjunctions(case.utterance)
    return SplitterCaseResult(
        case_id=case.case_id,
        utterance=case.utterance,
        should_split=case.should_split,
        actual_split=len(fragments) > 1,
        fragments=fragments,
    )


def run_splitter_eval(golden_set: list[SplitterCase] | None = None) -> SplitterEvalReport:
    golden_set = golden_set if golden_set is not None else SPLITTER_GOLDEN_SET
    return SplitterEvalReport(results=[_run_case(case) for case in golden_set])


if __name__ == "__main__":
    print(run_splitter_eval().summary())
