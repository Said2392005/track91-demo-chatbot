# ADR 002: LLM Client Strategy Pattern

## Status

Accepted

## Context

The tech stack requires a cheap default model for dev (originally planned as DeepSeek or Gemini
Flash-Lite) while staying provider-swappable, and explicitly forbids hardcoding one provider's
SDK into agent/service code. Response Generation, and potentially other future LLM-assisted
steps, need a single call shape regardless of which provider is behind it.

## Decision

Define an `LLMProvider` interface (protocol) in a provider-agnostic module, e.g.:

```
class LLMProvider(Protocol):
    async def generate(self, messages: list[Message], **kwargs) -> LLMResponse: ...
```

Each provider implements this interface in its own adapter module. Only adapter modules import
the provider's SDK. Provider selection happens once, at startup, via config/env (e.g.
`LLM_PROVIDER=bedrock`), resolved by a factory and injected into services via DI (Phase 11). No
node, service, or router ever imports a provider SDK directly or branches on provider name.

In practice, the strategy went through three providers before settling: `DeepSeekProvider` (the
original plan) was never given a paid key and was replaced with `GroqProvider`, a free-tier
OpenAI-compatible provider, for Phase 12's real-model verification. Both were later removed
in favor of `BedrockProvider` (`app/llm/providers/bedrock.py`, AWS Bedrock, gpt-oss-120b) — the
current and only configured real provider. Each swap was a config change (`LLM_PROVIDER=...`)
plus one new adapter module; nothing else in the codebase changed, which is the outcome this
pattern exists to guarantee. Bedrock's gpt-oss models emit a `<reasoning>...</reasoning> `block
that the adapter strips before the response reaches synthesis or the user, and their response
body is OpenAI-compatible in shape even though the transport is boto3, not HTTP — so usage
parsing (`app/llm/providers/usage.py`) is shared by shape, not by transport.

## Consequences

- Swapping the real model for a different one is a config change, not a code change — proven
  twice now (DeepSeek → Groq → Bedrock), not just a design claim.
- Adding a new provider means adding one adapter class; nothing else in the codebase changes.
- Provider-specific capabilities (e.g. function-calling formats) must be normalized behind the
  interface or explicitly left unsupported — the interface is intentionally the lowest common
  denominator (plain message-in, text-out), since routing/tool-calling is handled deterministically
  elsewhere (see [[003-deterministic-intent-routing]]), not via provider-specific function calling.
- A provider-specific quirk (Bedrock's hidden reasoning block) is normalized inside that
  provider's own adapter, not leaked into the shared interface — callers of `LLMProvider.generate()`
  never know or care that it exists.
