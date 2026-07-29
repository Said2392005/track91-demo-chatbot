"""
LLMProvider tests — no live API key or network access here (real-model verification is a
manual step, see docs/phase-12-testing/testing.md). DeepSeekProvider and GroqProvider both
subclass OpenAICompatibleProvider (app/llm/providers/openai_compatible.py), so their
request/response handling is verified once against DeepSeek's config and once against Groq's
to confirm each concrete adapter's api_base/default_model wiring, not to re-test shared logic
twice. The LLM-based intent classifier strategy is verified against FakeLLMProvider.
"""

import httpx
import pytest

from app.llm.base import Message
from app.llm.providers.deepseek import DeepSeekProvider
from app.llm.providers.fake import FakeLLMProvider
from app.llm.providers.groq import GroqProvider
from app.nlu.intent_classifier import LLMIntentClassifier


def test_deepseek_provider_requires_api_key():
    with pytest.raises(ValueError):
        DeepSeekProvider(api_key="")


async def test_deepseek_provider_builds_request_and_parses_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = request.read()
        return httpx.Response(
            200,
            json={
                "model": "deepseek-chat",
                "choices": [{"message": {"role": "assistant", "content": "hello back"}}],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.deepseek.com")
    provider = DeepSeekProvider(api_key="test-key", client=client)

    response = await provider.generate([Message(role="user", content="hi")])

    assert response.content == "hello back"
    assert response.model == "deepseek-chat"
    assert captured["auth"] == "Bearer test-key"
    assert captured["url"].endswith("/chat/completions")
    assert b'"hi"' in captured["body"]


async def test_deepseek_provider_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.deepseek.com")
    provider = DeepSeekProvider(api_key="bad-key", client=client)

    with pytest.raises(httpx.HTTPStatusError):
        await provider.generate([Message(role="user", content="hi")])


def test_groq_provider_requires_api_key():
    with pytest.raises(ValueError):
        GroqProvider(api_key="")


def test_groq_provider_defaults_to_the_documented_model_and_base_url():
    provider = GroqProvider(api_key="test-key")
    assert provider.api_base == "https://api.groq.com/openai/v1"
    assert provider.default_model == "llama-3.3-70b-versatile"


async def test_groq_provider_builds_request_and_parses_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = request.read()
        return httpx.Response(
            200,
            json={
                "model": "llama-3.3-70b-versatile",
                "choices": [{"message": {"role": "assistant", "content": "hello from groq"}}],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.groq.com/openai/v1")
    provider = GroqProvider(api_key="test-key", client=client)

    response = await provider.generate([Message(role="user", content="hi")])

    assert response.content == "hello from groq"
    assert response.model == "llama-3.3-70b-versatile"
    assert captured["auth"] == "Bearer test-key"
    assert captured["url"].endswith("/chat/completions")


async def test_groq_provider_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.groq.com/openai/v1")
    provider = GroqProvider(api_key="bad-key", client=client)

    with pytest.raises(httpx.HTTPStatusError):
        await provider.generate([Message(role="user", content="hi")])


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
