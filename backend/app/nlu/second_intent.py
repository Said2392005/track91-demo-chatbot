"""
Q2's "middle option" from the multi-intent tradeoff discussion — NOT wired into the main chat
pipeline yet. Detects whether a SECOND intent also scores meaningfully on the same utterance
the primary classifier already committed to, reusing the deterministic classifier's own scoring
(app/nlu/intent_classifier.py's score_all_intents()) rather than a separate, fragile
text-splitting heuristic. Approach 1 (conjunction-based splitting) was tried and rejected for
exactly that reason — see app/nlu/message_splitter.py's docstring and app/eval/splitter_eval.py's
measured 100% false-split rate on realistic negatives. Reusing the classifier's own trigger
scoring instead of guessing from punctuation is why this approach doesn't inherit that failure
mode: a negative case like "Show trips for Ramesh and Suresh" has nothing in it that scores for
any OTHER intent's triggers at all (second-best score 0), while a real compound request like
"list drivers and vehicle location" has a real second signal (score 2) — see
app/eval/second_intent_golden_set.py for the measured evidence behind SCORE_THRESHOLD below.

Pre-integration step only, per explicit instruction: this module and its eval
(app/eval/second_intent_golden_set.py, app/eval/second_intent_eval.py) measure false-positive
(on singles) and true-positive (on real pairs) rates before any decision to actually run a
second tool call in the graph.
"""

from app.nlu.intent_classifier import score_all_intents

# Chosen from real measured data (app/eval/second_intent_eval.py's report), not picked blind:
# every negative case's second-best score was 0; every detectable positive case's second-best
# score was 2 or 3. 2 is the natural boundary between "nothing else scored at all" and "a real
# second trigger fired."
SECOND_INTENT_SCORE_THRESHOLD = 2


def detect_second_intent(utterance: str, primary_intent: str, threshold: int = SECOND_INTENT_SCORE_THRESHOLD) -> str | None:
    """Returns the best-scoring intent other than primary_intent, if its score meets
    threshold — otherwise None. Never returns primary_intent itself."""
    scores = score_all_intents(utterance)
    scores.pop(primary_intent, None)
    if not scores:
        return None
    best_intent, best_score = max(scores.items(), key=lambda kv: kv[1])
    return best_intent if best_score >= threshold else None
