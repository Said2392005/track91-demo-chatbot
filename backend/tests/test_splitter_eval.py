"""
Golden-set-driven measurement of app/nlu/message_splitter.py's false-split rate — the
pre-integration check requested before this splitter goes anywhere near the main pipeline.

Verdict from the actual measured run (not aspirational): 100% false-split rate (7/7) on the
negative set — every "must not split" case, including the two specifically flagged during the
Approach 1 vs. Approach 2 tradeoff discussion (the EXPLAIN_FEATURE "and" case and the "Ramesh
and Suresh" two-driver case), got split anyway. A naive "split on and/also" rule cannot
distinguish "two intents joined by and" from "one intent whose content happens to contain and"
— which is exactly the semantic judgment Approach 2 exists to make, and Approach 1 was chosen
specifically to avoid building. This is a negative result, reported as requested rather than
shipped: this module is NOT wired into app/nlu/pipeline.py or the chat pipeline.

This test locks in that measured reality (not a "good enough" threshold) as a regression
baseline: if a future change to the splitting rule improves false_split_rate, this test's
threshold should be tightened to match, not loosened.
"""

from app.eval.splitter_eval import SplitterEvalReport, run_splitter_eval
from app.eval.splitter_golden_set import SPLITTER_GOLDEN_SET


def test_golden_set_has_negative_and_positive_cases():
    assert len(SPLITTER_GOLDEN_SET) >= 10
    negatives = [c for c in SPLITTER_GOLDEN_SET if not c.should_split]
    positives = [c for c in SPLITTER_GOLDEN_SET if c.should_split]
    assert len(negatives) >= 5
    assert len(positives) >= 5


def test_flagged_tradeoff_discussion_cases_are_both_present_as_negatives():
    """The two specific known-negative examples called out before this was built."""
    case_ids = {c.case_id for c in SPLITTER_GOLDEN_SET}
    assert "neg_explain_feature_and" in case_ids
    assert "neg_two_drivers" in case_ids


def test_measured_false_split_rate_matches_reported_finding():
    """Documents the actual measured result — not a threshold implying this is acceptable. See
    module docstring: 100% false-split rate, reported rather than shipped."""
    report: SplitterEvalReport = run_splitter_eval()
    assert report.false_split_rate == 1.0, (
        f"false_split_rate changed to {report.false_split_rate:.1%} — if this improved, "
        "tighten this assertion to match (see module docstring); if it's a real fix, this "
        "splitter may now be worth reconsidering for the main pipeline."
    )
    assert report.false_negative_rate == 0.0, "positive cases were previously all correctly split"


def test_every_flagged_negative_case_is_individually_confirmed_split():
    """Names the exact cases, not just the aggregate rate, so a partial improvement is visible
    case-by-case rather than only as a percentage."""
    report = run_splitter_eval()
    false_split_ids = {r.case_id for r in report.false_splits}
    for case in SPLITTER_GOLDEN_SET:
        if not case.should_split:
            assert case.case_id in false_split_ids, f"{case.case_id} no longer false-splits — good, update this test"
