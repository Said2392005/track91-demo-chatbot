# ADR 002: LLM Client Strategy Pattern

## Status

Accepted

## Context

The tech stack requires a cheap default model for dev (DeepSeek or Gemini Flash-Lite) while
staying provider-swappable, and explicitly forbids hardcoding one provider's SDK into
agent/service code. Response Generation, and potentially other future LLM-assisted steps, need
a single call shape regardless of which provider is behind it.

## Decision

Define an `LLMProvider` interface (protocol) in a provider-agnostic module, e.g.:

```
class LLMProvider(Protocol):
    async def generate(self, messages: list[Message], **kwargs) -> LLMResponse: ...
```

Each provider (DeepSeek, Gemini Flash-Lite, others later) implements this interface in its own
adapter module. Only adapter modules import the provider's SDK. Provider selection happens once,
at startup, via config/env (e.g. `LLM_PROVIDER=deepseek`), resolved by a factory and injected
into services via DI (Phase 11). No node, service, or router ever imports a provider SDK
directly or branches on provider name.

## Consequences

- Swapping the dev model for a different one is a config change, not a code change.
- Adding a new provider means adding one adapter class; nothing else in the codebase changes.
- Provider-specific capabilities (e.g. function-calling formats) must be normalized behind the
  interface or explicitly left unsupported — the interface is intentionally the lowest common
  denominator (plain message-in, text-out), since routing/tool-calling is handled deterministically
  elsewhere (see [[003-deterministic-intent-routing]]), not via provider-specific function calling.
