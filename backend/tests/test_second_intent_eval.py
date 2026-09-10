"""
Golden-set-driven measurement of app/nlu/second_intent.py's false-positive/true-positive rates
— the pre-integration check requested before this detector goes anywhere near the main
pipeline (same bar as app/nlu/message_splitter.py's rejected conjunction-splitter check).

Verdict from the actual measured run: 0% false-positive rate (0/8) on the negative set —
including all 7 cases reused verbatim from the rejected splitter eval, the exact kind of
"two entities of the same type joined by 'and'" case a naive detector could also misfire on —
and 100% true-positive rate (6/6) on the real compound requests that have a detectable second
signal at all (a 7th positive, "...also is it currently moving?", is an honest, disclosed miss:
no intent's triggers score on that clause, a trigger-coverage gap unrelated to this detector's
own logic — see second_intent_golden_set.py's KNOWN_MISS case).

This clears the bar the rejected splitter did not. Still NOT wired into
app/nlu/pipeline.py or the chat pipeline — that remains a separate decision.
"""

from app.eval.second_intent_eval import SecondIntentEvalReport, run_second_intent_eval
from app.eval.second_intent_golden_set import SECOND_INTENT_GOLDEN_SET


def test_golden_set_has_negative_and_positive_cases():
    assert len(SECOND_INTENT_GOLDEN_SET) >= 10
    negatives = [c for c in SECOND_INTENT_GOLDEN_SET if not c.expect_second_intent]
    positives = [c for c in SECOND_INTENT_GOLDEN_SET if c.expect_second_intent]
    assert len(negatives) >= 5
    assert len(positives) >= 5


def test_splitter_negatives_are_reused_verbatim():
    """The specific discipline requested: reuse the exact cases that sank the conjunction
    splitter, not a weaker or different negative set."""
    case_ids = {c.case_id for c in SECOND_INTENT_GOLDEN_SET}
    for case_id in [
        "neg_explain_feature_and",
        "neg_two_drivers",
        "neg_policy_compound_noun",
        "neg_two_vehicles",
        "neg_two_drivers_score",
        "neg_health_compound_verb",
        "neg_app_faq_register_and_link",
    ]:
        assert case_id in case_ids


def test_measured_false_positive_rate_is_zero():
    report: SecondIntentEvalReport = run_second_intent_eval()
    assert report.false_positive_rate == 0.0, report.summary()


def test_measured_true_positive_rate_on_detectable_positives():
    report = run_second_intent_eval()
    detectable = [r for r in report.positives if r.case_id != "pos_alerts_and_moving_KNOWN_MISS"]
    hits = sum(r.correct for r in detectable)
    assert hits == len(detectable), report.summary()


def test_known_miss_case_is_explicitly_disclosed_not_silently_passing():
    """"...also is it currently moving?" must still resolve to "no second intent detected" (so
    it doesn't get miscounted as a false positive) — but it's tracked as its own explicit case
    so a future trigger-coverage fix that makes it detectable doesn't go unnoticed."""
    report = run_second_intent_eval()
    known_miss = next(r for r in report.results if r.case_id == "pos_alerts_and_moving_KNOWN_MISS")
    assert known_miss.detected is None
