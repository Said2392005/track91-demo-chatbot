"""get_llm_provider() dispatch tests — never raises, falls back to UnavailableLLMProvider for a
bad config or an unknown provider name."""

from botocore.exceptions import ProfileNotFound

from app.core.config import settings
from app.llm.factory import get_llm_provider
from app.llm.providers.bedrock import BedrockProvider
from app.llm.providers.unavailable import UnavailableLLMProvider


def _fresh_provider(monkeypatch, **settings_overrides):
    for key, value in settings_overrides.items():
        monkeypatch.setattr(settings, key, value)
    get_llm_provider.cache_clear()
    provider = get_llm_provider()
    get_llm_provider.cache_clear()
    return provider


def test_unknown_provider_name_falls_back_to_unavailable(monkeypatch):
    provider = _fresh_provider(monkeypatch, llm_provider="not-a-real-provider")
    assert isinstance(provider, UnavailableLLMProvider)


def test_bedrock_with_config_returns_bedrock_provider(monkeypatch):
    # aws_profile="" (default credential chain, not a named profile) deliberately, so this test
    # doesn't depend on an "office" AWS profile actually existing on whatever machine runs the
    # suite — boto3.Session(profile_name=None) never eagerly validates anything, unlike a named
    # profile (see test_bedrock_with_unresolvable_profile_falls_back_to_unavailable below).
    provider = _fresh_provider(
        monkeypatch,
        llm_provider="bedrock",
        bedrock_model_id="arn:aws:bedrock:ap-south-1::inference-profile/apac.amazon.nova-lite-v1:0",
        bedrock_region="ap-south-1",
        aws_profile="",
    )
    assert isinstance(provider, BedrockProvider)


def test_bedrock_with_empty_model_id_falls_back_to_unavailable(monkeypatch):
    """Unlike Groq's api_key, bedrock_model_id/bedrock_region always have non-empty code
    defaults, so this path is only reachable via an explicit empty override — still worth
    covering since _build_bedrock constructs a real boto3 client with no api-key-style
    short-circuit of its own; BedrockProvider.__init__'s own validation is what get_llm_provider
    relies on to turn a bad config into UnavailableLLMProvider instead of crashing app startup."""
    provider = _fresh_provider(
        monkeypatch, llm_provider="bedrock", bedrock_model_id="", bedrock_region="ap-south-1", aws_profile=""
    )
    assert isinstance(provider, UnavailableLLMProvider)


def test_bedrock_with_unresolvable_profile_falls_back_to_unavailable(monkeypatch):
    """Real bug, found by actually triggering this path (not by inspection): boto3.Session(
    profile_name=...) (bedrock.py) raises botocore.exceptions.ProfileNotFound immediately at
    construction for a profile that doesn't exist in ~/.aws/credentials or ~/.aws/config —
    eagerly, unlike the old boto3.client() call it replaced, which deferred all credential
    errors to the first real API call. A misspelled aws_profile must degrade to
    UnavailableLLMProvider the same way any other bad LLM config does here, not crash the whole
    app at startup — see app/llm/factory.py's except clause."""
    provider = _fresh_provider(
        monkeypatch,
        llm_provider="bedrock",
        bedrock_model_id="arn:aws:bedrock:ap-south-1::inference-profile/apac.amazon.nova-lite-v1:0",
        bedrock_region="ap-south-1",
        aws_profile="this-profile-almost-certainly-does-not-exist-anywhere",
    )
    assert isinstance(provider, UnavailableLLMProvider)


def test_profile_not_found_is_a_botocore_error_not_a_value_error():
    """Documents *why* factory.py's except clause needs BotoCoreError specifically, not just
    ValueError — a regression here would silently reopen the crash-on-bad-profile bug above."""
    assert not issubclass(ProfileNotFound, ValueError)
