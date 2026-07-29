"""
Approach 1 (scoped narrowly, per the tradeoff discussion this followed): hard-splits an
utterance on explicit "and"/"also" conjunctions, so a compound request like "list my drivers
and also show vehicle locations" can be run as separate sequential turns through the existing
single-intent pipeline unchanged.

Deliberately naive, not a general parser: it splits on every standalone occurrence of "and" or
"also", with no attempt to distinguish "two intents joined by and" from "one intent whose
kb_topic/entity value happens to contain and" (e.g. "trip and location history", "Ramesh and
Suresh"). That disambiguation is exactly what app/eval/splitter_golden_set.py + splitter_eval.py
measure empirically (false-split rate) rather than what this function tries to solve itself —
see the tradeoff discussion: building real disambiguation here is Approach 2's cost, not
Approach 1's.

NOT wired into the main chat pipeline yet — this module and its eval are a standalone
pre-integration step, per explicit instruction to measure the false-split rate before trusting
it in production.
"""

import re

# \b, not surrounding \s+, so "and"/"also" at the very start/end of the utterance (unlikely in
# practice, but not assumed) still matches; leading/trailing whitespace on each fragment is
# cleaned up separately.
_SPLIT_PATTERN = re.compile(r"\b(?:and|also)\b", re.IGNORECASE)


def split_conjunctions(utterance: str) -> list[str]:
    """Returns [utterance] unchanged (a list of one) when no split conjunction is found, so a
    caller can treat "not split" and "split into one fragment" identically without a separate
    branch."""
    fragments = [f.strip(" ,.;") for f in _SPLIT_PATTERN.split(utterance.strip())]
    fragments = [f for f in fragments if f]
    return fragments if len(fragments) > 1 else [utterance.strip()]
