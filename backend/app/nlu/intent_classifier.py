"""
Intent classification — two swappable strategies behind one interface, per the Phase 1
clarification: rule-based ships as the default (fully offline-testable, no API key required);
LLM-based is available as a config-driven alternative once real credentials exist.

Neither strategy decides which system of record to hit — that's the Phase 9 router's job alone
(ADR 003). Classification only maps utterance text to one label from the fixed taxonomy.
"""

import json
import re
from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.taxonomy import ALL_INTENTS
from app.llm.base import LLMProvider, Message
from app.nlu.trigger_patterns import (
    AFFIRM_DENY_PHRASES,
    DOMAIN_ADJACENT_KEYWORDS,
    TRIGGER_COOCCURRENCE,
    TRIGGER_PHRASES,
    TRIGGER_REGEXES,
)

# Priority order for tie-breaking: category order from taxonomy (A -> E), backlog intents
# interleaved in their taxonomy position.
_PRIORITY_ORDER = [i for i in ALL_INTENTS if i not in ("CLARIFICATION_NEEDED", "AFFIRM_DENY")]


class IntentClassifier(ABC):
    @abstractmethod
    async def classify(self, utterance: str, session_state: dict | None = None) -> str: ...


@lru_cache(maxsize=None)
def _phrase_regex(phrase: str) -> re.Pattern:
    # Word-boundary match, not naive substring — "hi" must not match inside "vehicles"/"this"/
    # "Delhi"/"anything" (a real bug caught by the paraphrase test suite: see commit history).
    return re.compile(r"\b" + re.escape(phrase) + r"\b")


def _score(utterance_lower: str, intent: str) -> int:
    score = 0
    for phrase in TRIGGER_PHRASES.get(intent, []):
        if _phrase_regex(phrase).search(utterance_lower):
            score += len(phrase.split())
    for pattern in TRIGGER_REGEXES.get(intent, []):
        if pattern.search(utterance_lower):
            score += 3
    cooccurrence = TRIGGER_COOCCURRENCE.get(intent)
    if cooccurrence:
        verbs, subjects = cooccurrence
        if any(_phrase_regex(v).search(utterance_lower) for v in verbs) and any(
            _phrase_regex(s).search(utterance_lower) for s in subjects
        ):
            score += 4
    return score


class RuleBasedIntentClassifier(IntentClassifier):
    async def classify(self, utterance: str, session_state: dict | None = None) -> str:
        lowered = utterance.strip().lower()
        session_state = session_state or {}

        if session_state.get("awaiting_clarification") and any(
            phrase == lowered or lowered.startswith(phrase + " ") or lowered.startswith(phrase + ",")
            for phrase in AFFIRM_DENY_PHRASES
        ):
            return "AFFIRM_DENY"

        best_intent, best_score = None, 0
        for intent in _PRIORITY_ORDER:
            score = _score(lowered, intent)
            if score > best_score:
                best_intent, best_score = intent, score

        if best_intent is not None:
            return best_intent

        if any(keyword in lowered for keyword in DOMAIN_ADJACENT_KEYWORDS):
            return "GENERAL_KNOWLEDGE"

        return "OUT_OF_SCOPE"


_LLM_SYSTEM_PROMPT = (
    "You are an intent classifier for a fleet-management chatbot. Given a user message, "
    "respond with EXACTLY ONE label from this list, and nothing else:\n"
    + ", ".join(ALL_INTENTS)
)


class LLMIntentClassifier(IntentClassifier):
    """Alternative strategy behind the same interface — selected via
    settings.intent_classifier_strategy == "llm". Not exercised against a live provider in
    this build (no API credentials configured); tested against FakeLLMProvider instead to
    verify prompt construction and response parsing."""

    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def classify(self, utterance: str, session_state: dict | None = None) -> str:
        response = await self._llm.generate(
            [
                Message(role="system", content=_LLM_SYSTEM_PROMPT),
                Message(role="user", content=utterance),
            ],
            call_type="intent_classification",
        )
        label = response.content.strip().strip('"').strip()
        # Tolerate a JSON-wrapped reply (e.g. {"intent": "GET_VEHICLE_SPEED"}) without requiring it.
        if label.startswith("{"):
            try:
                label = json.loads(label).get("intent", label)
            except (json.JSONDecodeError, AttributeError):
                pass

        if label in ALL_INTENTS:
            return label
        return "OUT_OF_SCOPE"


def get_intent_classifier(llm: LLMProvider | None = None) -> IntentClassifier:
    """`llm`, when passed, overrides the default app.llm.factory.get_llm_provider() singleton
    — app/main.py passes the usage-tracking-wrapped provider here so LLM-strategy
    classification is tracked identically to every other real LLM call, instead of silently
    picking up the unwrapped cached singleton on its own."""
    from app.core.config import settings

    if settings.intent_classifier_strategy == "llm":
        if llm is None:
            from app.llm.factory import get_llm_provider

            llm = get_llm_provider()
        return LLMIntentClassifier(llm)
    return RuleBasedIntentClassifier()
