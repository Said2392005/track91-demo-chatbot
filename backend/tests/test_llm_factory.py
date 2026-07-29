"""get_llm_provider() dispatch tests — never raises, falls back to UnavailableLLMProvider for a
missing key or an unknown provider name."""

from app.core.config import settings
from app.llm.factory import get_llm_provider
from app.llm.providers.deepseek import DeepSeekProvider
from app.llm.providers.groq import GroqProvider
from app.llm.providers.unavailable import UnavailableLLMProvider


def _fresh_provider(monkeypatch, **settings_overrides):
    for key, value in settings_overrides.items():
        monkeypatch.setattr(settings, key, value)
    get_llm_provider.cache_clear()
    provider = get_llm_provider()
    get_llm_provider.cache_clear()
    return provider


def test_deepseek_with_key_returns_deepseek_provider(monkeypatch):
    provider = _fresh_provider(monkeypatch, llm_provider="deepseek", deepseek_api_key="real-key")
    assert isinstance(provider, DeepSeekProvider)


def test_groq_with_key_returns_groq_provider(monkeypatch):
    provider = _fresh_provider(monkeypatch, llm_provider="groq", groq_api_key="real-key")
    assert isinstance(provider, GroqProvider)


def test_deepseek_without_key_falls_back_to_unavailable(monkeypatch):
    provider = _fresh_provider(monkeypatch, llm_provider="deepseek", deepseek_api_key="")
    assert isinstance(provider, UnavailableLLMProvider)


def test_groq_without_key_falls_back_to_unavailable(monkeypatch):
    provider = _fresh_provider(monkeypatch, llm_provider="groq", groq_api_key="")
    assert isinstance(provider, UnavailableLLMProvider)


def test_unknown_provider_name_falls_back_to_unavailable(monkeypatch):
    provider = _fresh_provider(monkeypatch, llm_provider="not-a-real-provider")
    assert isinstance(provider, UnavailableLLMProvider)
