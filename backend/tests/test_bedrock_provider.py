"""
BedrockProvider tests — no live AWS call or credentials here (real-model verification is a
manual step, see tests/test_max_tokens_real_bedrock.py for the opt-in real-call tests). The
real boto3 client is replaced with a minimal fake exposing converse(modelId, system, messages,
inferenceConfig) -> a plain dict, matching Converse's actual response shape (unlike the old
invoke_model API this replaced, Converse returns a parsed dict directly — no streaming body to
.read()).

No reasoning-stripping tests here, unlike the previous gpt-oss/invoke_model iteration: that
behavior was specific to gpt-oss's harmony/channel response format, not a Converse or Nova
behavior — see bedrock.py's module docstring for why it was removed rather than kept as unused
defensive code.

The profile-vs-default-chain tests (below the main block) monkeypatch boto3.Session itself,
since that's the one thing __init__ does before a `client=` override would even apply — passing
`client=` (as every test above does) skips the `boto3.Session(...).client(...)` call in __init__
entirely, which is exactly why those tests never needed to touch boto3.Session at all.
"""

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from app.llm.base import Message
from app.llm.providers.bedrock import BedrockProvider

MODEL_ID = "arn:aws:bedrock:ap-south-1::inference-profile/apac.amazon.nova-lite-v1:0"


class _FakeBedrockClient:
    def __init__(self, response_data: dict | None = None, error: Exception | None = None):
        self._response_data = response_data
        self._error = error
        self.received_calls: list[dict] = []

    def converse(self, modelId: str, system: list, messages: list, inferenceConfig: dict):
        self.received_calls.append(
            {"modelId": modelId, "system": system, "messages": messages, "inferenceConfig": inferenceConfig}
        )
        if self._error is not None:
            raise self._error
        return self._response_data


def _response(text: str, usage: dict | None = None) -> dict:
    data: dict = {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": "end_turn",
    }
    if usage is not None:
        data["usage"] = usage
    return data


def test_bedrock_provider_requires_model_id():
    with pytest.raises(ValueError):
        BedrockProvider(model_id="", region="ap-south-1")


def test_bedrock_provider_requires_region():
    with pytest.raises(ValueError):
        BedrockProvider(model_id=MODEL_ID, region="")


async def test_bedrock_provider_builds_request_and_parses_response():
    client = _FakeBedrockClient(_response("hello from nova"))
    provider = BedrockProvider(model_id=MODEL_ID, region="ap-south-1", client=client)

    response = await provider.generate([Message(role="user", content="hi")])

    assert response.content == "hello from nova"
    assert response.model == MODEL_ID
    call = client.received_calls[0]
    assert call["modelId"] == MODEL_ID
    assert call["messages"] == [{"role": "user", "content": [{"text": "hi"}]}]
    assert call["system"] == []


async def test_bedrock_provider_splits_system_messages_into_the_converse_system_param():
    """Converse keeps system prompts out of `messages` entirely — a separate top-level `system`
    param, unlike the old invoke_model body which just put every role (including "system")
    straight into one flat messages list."""
    client = _FakeBedrockClient(_response("ok"))
    provider = BedrockProvider(model_id=MODEL_ID, region="ap-south-1", client=client)

    await provider.generate(
        [Message(role="system", content="You are a helpful assistant."), Message(role="user", content="hi")]
    )

    call = client.received_calls[0]
    assert call["system"] == [{"text": "You are a helpful assistant."}]
    assert call["messages"] == [{"role": "user", "content": [{"text": "hi"}]}]


async def test_bedrock_provider_preserves_multi_turn_conversation_order():
    client = _FakeBedrockClient(_response("ok"))
    provider = BedrockProvider(model_id=MODEL_ID, region="ap-south-1", client=client)

    await provider.generate(
        [
            Message(role="system", content="Be concise."),
            Message(role="user", content="where is MH12AB1234?"),
            Message(role="assistant", content="It's near Pimpri, Pune."),
            Message(role="user", content="what's its speed?"),
        ]
    )

    call = client.received_calls[0]
    assert call["system"] == [{"text": "Be concise."}]
    assert call["messages"] == [
        {"role": "user", "content": [{"text": "where is MH12AB1234?"}]},
        {"role": "assistant", "content": [{"text": "It's near Pimpri, Pune."}]},
        {"role": "user", "content": [{"text": "what's its speed?"}]},
    ]


async def test_bedrock_provider_passes_temperature_and_max_tokens_through():
    client = _FakeBedrockClient(_response("ok"))
    provider = BedrockProvider(model_id=MODEL_ID, region="ap-south-1", client=client)

    await provider.generate([Message(role="user", content="hi")], temperature=0.7, max_tokens=42)

    inference_config = client.received_calls[0]["inferenceConfig"]
    assert inference_config["temperature"] == 0.7
    assert inference_config["maxTokens"] == 42


async def test_bedrock_provider_defaults_temperature_and_max_tokens_when_not_passed():
    client = _FakeBedrockClient(_response("ok"))
    provider = BedrockProvider(model_id=MODEL_ID, region="ap-south-1", client=client)

    await provider.generate([Message(role="user", content="hi")])

    inference_config = client.received_calls[0]["inferenceConfig"]
    assert inference_config["temperature"] == 0.2
    assert inference_config["maxTokens"] == 512


async def test_bedrock_provider_parses_usage():
    client = _FakeBedrockClient(_response("hi", usage={"inputTokens": 74, "outputTokens": 53, "totalTokens": 127}))
    provider = BedrockProvider(model_id=MODEL_ID, region="ap-south-1", client=client)

    response = await provider.generate([Message(role="user", content="hi")])

    assert response.usage is not None
    assert response.usage.prompt_tokens == 74
    assert response.usage.completion_tokens == 53


async def test_bedrock_provider_returns_none_usage_when_missing():
    client = _FakeBedrockClient(_response("hi"))  # no "usage" key at all
    provider = BedrockProvider(model_id=MODEL_ID, region="ap-south-1", client=client)

    response = await provider.generate([Message(role="user", content="hi")])

    assert response.usage is None


async def test_bedrock_provider_propagates_client_error():
    error = ClientError(
        error_response={"Error": {"Code": "ThrottlingException", "Message": "Too many requests"}},
        operation_name="Converse",
    )
    client = _FakeBedrockClient(error=error)
    provider = BedrockProvider(model_id=MODEL_ID, region="ap-south-1", client=client)

    with pytest.raises(ClientError):
        await provider.generate([Message(role="user", content="hi")])


class _FakeSession:
    """Stands in for boto3.Session — records the profile_name it was constructed with and
    hands back whatever fake client the test configured, keyed by AWS service name."""

    last_profile_name: str | None = "not-yet-called"

    def __init__(self, profile_name=None):
        _FakeSession.last_profile_name = profile_name
        self.profile_name = profile_name

    def client(self, service_name: str, region_name: str | None = None):
        return _FakeSession.clients_by_service[service_name]


async def test_bedrock_provider_builds_its_client_from_the_named_profile(monkeypatch):
    """No AWS_PROFILE shell dependency: the profile is baked into the boto3.Session call
    itself, from settings.aws_profile — this is the actual fix for "works in one terminal,
    NoCredentialsError in a new one"."""
    _FakeSession.clients_by_service = {"bedrock-runtime": _FakeBedrockClient(_response("ok"))}
    monkeypatch.setattr("app.llm.providers.bedrock.boto3.Session", _FakeSession)

    BedrockProvider(model_id=MODEL_ID, region="ap-south-1", profile="office")

    assert _FakeSession.last_profile_name == "office"


async def test_bedrock_provider_falls_back_to_default_credential_chain_when_profile_is_empty(monkeypatch):
    """profile="" (the production/container setting — see config.py's aws_profile comment) must
    reach boto3.Session as profile_name=None, its own signal to use the default credential
    chain (env vars, ~/.aws/credentials [default], or an IAM role) instead of a named profile
    that won't exist in that environment."""
    _FakeSession.clients_by_service = {"bedrock-runtime": _FakeBedrockClient(_response("ok"))}
    monkeypatch.setattr("app.llm.providers.bedrock.boto3.Session", _FakeSession)

    BedrockProvider(model_id=MODEL_ID, region="ap-south-1", profile="")

    assert _FakeSession.last_profile_name is None


async def test_bedrock_provider_falls_back_to_default_credential_chain_when_profile_is_not_passed(monkeypatch):
    """Same as above, via the constructor default rather than an explicit empty string."""
    _FakeSession.clients_by_service = {"bedrock-runtime": _FakeBedrockClient(_response("ok"))}
    monkeypatch.setattr("app.llm.providers.bedrock.boto3.Session", _FakeSession)

    BedrockProvider(model_id=MODEL_ID, region="ap-south-1")

    assert _FakeSession.last_profile_name is None


async def test_verify_credentials_succeeds_when_sts_call_resolves(monkeypatch):
    class _FakeSTS:
        def get_caller_identity(self):
            return {"Account": "123456789012", "Arn": "arn:aws:iam::123456789012:user/office"}

    _FakeSession.clients_by_service = {"sts": _FakeSTS()}
    monkeypatch.setattr("app.llm.providers.bedrock.boto3.Session", _FakeSession)
    provider = BedrockProvider(model_id=MODEL_ID, region="ap-south-1", profile="office", client=_FakeBedrockClient(_response("ok")))

    await provider.verify_credentials()  # must not raise

    assert _FakeSession.last_profile_name == "office"


async def test_verify_credentials_propagates_no_credentials_error(monkeypatch):
    """The exact failure this whole feature is about: verify_credentials() must surface it
    clearly (not swallow it) so callers (app/main.py's startup check, the standalone CLI) can
    detect and report it."""

    class _FakeSTS:
        def get_caller_identity(self):
            raise NoCredentialsError()

    _FakeSession.clients_by_service = {"sts": _FakeSTS()}
    monkeypatch.setattr("app.llm.providers.bedrock.boto3.Session", _FakeSession)
    provider = BedrockProvider(model_id=MODEL_ID, region="ap-south-1", profile="office", client=_FakeBedrockClient(_response("ok")))

    with pytest.raises(NoCredentialsError):
        await provider.verify_credentials()
