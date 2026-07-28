"""
LLMProvider interface — ADR 002 (docs/phase-2-architecture/adr/002-llm-strategy-pattern.md).

Only adapter modules (app/llm/providers/*) may import a provider SDK or construct provider-
specific HTTP requests. Everything else in the codebase — including the Phase 6 LLM-based
intent classifier and, later, the Phase 7 generation node — depends only on this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


@dataclass
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    raw: dict | None = None


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, messages: list[Message], **kwargs) -> LLMResponse: ...
