"""
Groq adapter — OpenAI-compatible chat completions HTTP API, free-tier. Used as the actual
real-model provider for Phase 12's held-open "verify against a real model" check, since a paid
DeepSeek key wasn't available. Not part of the roadmap's originally-named stack (DeepSeek /
Gemini Flash-Lite), but fits the same "cheap/free dev-model behind the LLMProvider interface"
requirement exactly — swapping it in is a config change (LLM_PROVIDER=groq), not a code change,
per ADR 002.
"""

from app.llm.providers.openai_compatible import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):
    api_base = "https://api.groq.com/openai/v1"
    default_model = "llama-3.3-70b-versatile"
