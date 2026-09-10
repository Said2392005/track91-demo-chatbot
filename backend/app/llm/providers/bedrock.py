"""
AWS Bedrock adapter (ADR 002), via Bedrock's Converse API — converse(), not invoke_model(),
matching the exact call shape specified by the reference Node.js implementation (AWS SDK v3's
BedrockRuntimeClient + ConverseCommand). Model is Amazon Nova Lite, addressed by its APAC
inference profile ARN (on-demand invocation of some models/regions requires an inference profile
rather than the bare model ID) in ap-south-1 — not gpt-oss-120b/us-east-1, which this adapter
used previously; see git history / docs/phase-12-testing/testing.md for that prior iteration.

No <reasoning> stripping here, unlike the previous gpt-oss iteration: that was specific to
gpt-oss's harmony/channel response format (a hidden chain-of-thought block gpt-oss emits before
its visible answer), not a general Bedrock or Converse behavior. Nova's Converse responses don't
have an equivalent hidden block, and the reference implementation doesn't strip anything either
— it parses response.output.message.content[0].text directly. Flagged as not yet re-confirmed
against a real live call for *this* model specifically (see this change's rollout notes) — the
prior gpt-oss finding was verified live; this one is based on Nova's documented Converse
response shape and the reference implementation, not a fresh live observation.

Credentials come from an explicit boto3 profile (settings.aws_profile, default "office" — see
app/core/config.py) rather than boto3's default chain picking up whatever AWS_PROFILE happens to
be exported in the current shell. Set aws_profile="" (production/containers) to fall back to the
default chain (env vars, ~/.aws/credentials [default], or an IAM role) instead of forcing a
named profile that won't exist there.

Error handling: converse() raises botocore.exceptions.ClientError (ThrottlingException,
ValidationException, AccessDeniedException, ModelTimeoutException, etc.) on any non-2xx
response — deliberately left to propagate uncaught, the same way an httpx-based adapter would
leave response.raise_for_status() uncaught. See test_bedrock_provider.py.

Credential pre-flight: verify_credentials() below does a cheap sts:GetCallerIdentity call (no
model invocation, no cost) to confirm credentials actually resolve. app/main.py's lifespan calls
it at real app startup and logs loudly on failure without blocking startup — this module's own
`python -m app.llm.providers.bedrock` CLI does the hard-fail version (non-zero exit), for a
pre-deploy/CI check or manual troubleshooting where an actual stop is wanted. The app itself
never hard-fails on a bad LLM config, by design (see app/llm/factory.py's docstring) — this CLI
is the deliberate exception, run on purpose, not something the app calls itself.
"""
import asyncio

import boto3

from app.llm.base import LLMProvider, LLMResponse, Message, TokenUsage


def _parse_converse_usage(response: dict) -> TokenUsage | None:
    # Converse's own usage shape: {"usage": {"inputTokens": N, "outputTokens": N,
    # "totalTokens": N}} — named differently from the OpenAI-compatible prompt_tokens/
    # completion_tokens shape the previous gpt-oss/invoke_model iteration parsed. Missing
    # entirely, or missing one of the two counts, is treated the same way: no usage data, not a
    # crash and not a guessed 0.
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("inputTokens")
    output_tokens = usage.get("outputTokens")
    if input_tokens is None and output_tokens is None:
        return None
    return TokenUsage(prompt_tokens=input_tokens, completion_tokens=output_tokens)


class BedrockProvider(LLMProvider):
    def __init__(self, model_id: str, region: str, profile: str | None = None, client=None):
        if not model_id:
            raise ValueError("BedrockProvider requires a non-empty model_id")
        if not region:
            raise ValueError("BedrockProvider requires a non-empty region")
        self._model_id = model_id
        self._region = region
        # "" (production/container default, see config.py) normalizes to None here, which is
        # boto3.Session's own signal to use its default credential chain instead of a named
        # profile — not a special case this module has to implement itself.
        self._profile = profile or None
        self._client = client or boto3.Session(profile_name=self._profile).client(
            "bedrock-runtime", region_name=region
        )

    async def verify_credentials(self) -> None:
        """Cheap pre-flight check: confirms credentials actually resolve for this provider's
        configured profile/region without invoking the model. Raises the same
        botocore.exceptions.NoCredentialsError / ClientError a real generate() call would
        eventually hit — just synchronously, before anything depends on it working."""
        sts = boto3.Session(profile_name=self._profile).client("sts", region_name=self._region)
        await asyncio.to_thread(sts.get_caller_identity)

    async def generate(self, messages: list[Message], **kwargs) -> LLMResponse:
        # Converse keeps system prompts out of `messages` entirely (its own top-level `system`
        # param) — messages only ever carries user/assistant turns. Matches the reference
        # implementation's system=[{text: systemPrompt}] / messages split.
        system = [{"text": m.content} for m in messages if m.role == "system"]
        conversation = [{"role": m.role, "content": [{"text": m.content}]} for m in messages if m.role != "system"]

        # boto3 is synchronous — keep it off the event loop.
        response = await asyncio.to_thread(
            self._client.converse,
            modelId=self._model_id,
            system=system,
            messages=conversation,
            inferenceConfig={
                "temperature": kwargs.get("temperature", 0.2),
                "maxTokens": kwargs.get("max_tokens", 512),
            },
        )
        content = response["output"]["message"]["content"][0]["text"]
        return LLMResponse(
            content=content,
            model=self._model_id,
            raw=response,
            usage=_parse_converse_usage(response),
        )


def _cli() -> None:
    """Standalone credential pre-flight check: `python -m app.llm.providers.bedrock`. Exits
    non-zero with a clear message if Bedrock credentials can't be resolved at all — for a
    pre-deploy/CI check or manual troubleshooting. Deliberately hard-fails, unlike the app
    itself (get_llm_provider() never raises — see app/llm/factory.py's docstring): this script
    exists specifically so "credentials are broken" is caught here, on purpose, rather than
    hours later when a real chat message happens to need one."""
    import sys

    from app.core.config import settings

    profile_desc = settings.aws_profile or "(default credential chain)"
    print(
        f"Checking Bedrock credentials — model={settings.bedrock_model_id} "
        f"region={settings.bedrock_region} profile={profile_desc}"
    )
    try:
        # Construction itself can fail here — e.g. boto3.Session(profile_name=...) raises
        # ProfileNotFound immediately for a misspelled aws_profile, before verify_credentials()
        # ever runs — so it's inside the same try/except, not run separately beforehand.
        provider = BedrockProvider(
            model_id=settings.bedrock_model_id, region=settings.bedrock_region, profile=settings.aws_profile
        )
        asyncio.run(provider.verify_credentials())
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    print("OK — Bedrock credentials resolved successfully.")


if __name__ == "__main__":
    _cli()
