"""
LLMProvider interface tests that don't need a live API key or network access — real-model
verification is a manual step, see docs/phase-12-testing/testing.md. The concrete adapter
(BedrockProvider, app/llm/providers/bedrock.py) has its own dedicated tests in
test_bedrock_provider.py; this file covers FakeLLMProvider and the LLM-based intent classifier
strategy against it.
"""

from app.llm.base import Message
from app.llm.providers.fake import FakeLLMProvider
from app.nlu.intent_classifier import LLMIntentClassifier


async def test_fake_llm_provider_returns_canned_response_and_records_calls():
    fake = FakeLLMProvider(canned_response="GET_VEHICLE_SPEED")
    response = await fake.generate([Message(role="user", content="how fast is it?")])
    assert response.content == "GET_VEHICLE_SPEED"
    assert len(fake.received_calls) == 1


async def test_llm_intent_classifier_returns_valid_label_from_fake_provider():
    fake = FakeLLMProvider(canned_response="GET_VEHICLE_LOCATION")
    classifier = LLMIntentClassifier(fake)
    result = await classifier.classify("where is my truck")
    assert result == "GET_VEHICLE_LOCATION"


async def test_llm_intent_classifier_parses_json_wrapped_response():
    fake = FakeLLMProvider(canned_response='{"intent": "GET_VEHICLE_SPEED"}')
    classifier = LLMIntentClassifier(fake)
    result = await classifier.classify("how fast")
    assert result == "GET_VEHICLE_SPEED"


async def test_llm_intent_classifier_falls_back_to_out_of_scope_on_invalid_label():
    fake = FakeLLMProvider(canned_response="NOT_A_REAL_INTENT")
    classifier = LLMIntentClassifier(fake)
    result = await classifier.classify("gibberish")
    assert result == "OUT_OF_SCOPE"


async def test_get_intent_classifier_uses_the_passed_llm_override(monkeypatch):
    """app/main.py passes the usage-tracking-wrapped provider here so LLM-strategy
    classification is tracked like every other real LLM call, instead of silently picking up
    the unwrapped get_llm_provider() singleton on its own."""
    from app.core.config import settings
    from app.nlu.intent_classifier import get_intent_classifier

    monkeypatch.setattr(settings, "intent_classifier_strategy", "llm")
    fake = FakeLLMProvider(canned_response="GREETING")

    classifier = get_intent_classifier(llm=fake)

    assert isinstance(classifier, LLMIntentClassifier)
    assert classifier._llm is fake
