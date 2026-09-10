"""
Real, live verification that settings.llm_max_tokens doesn't truncate the realistic long-answer
cases on Bedrock — the Bedrock counterpart to the now-deleted test_max_tokens_real_groq.py.
Opt-in on AWS credentials being resolvable via boto3's default chain, per this suite's "no live
API calls by default" policy.

NOT YET RE-VERIFIED against Amazon Nova Lite specifically. This file (thresholds, the
_looks_complete() typography workaround, and llm_max_tokens=500 itself in app/core/config.py)
was tuned against the previous provider iteration — gpt-oss-120b via invoke_model, which spent
completion tokens on a hidden <reasoning> block before its visible answer and had its own
distinctive typography (narrow no-break spaces, curly quotes, full-width citation brackets).
Nova Lite via Converse doesn't have that reasoning-token tax (see bedrock.py's module docstring)
and its own real output hasn't been observed live yet — this account's daily Bedrock token quota
was already exhausted (same "Too many tokens per day" ThrottlingException seen with gpt-oss)
before this could be re-measured against Nova Lite. The response-shape fix below (stopReason,
not choices[0].finish_reason) IS confirmed correct — that's Converse's documented shape, not a
guess — but the actual truncation-rate numbers and 500-token cap need re-confirming against Nova
Lite once quota allows, the same rigor the gpt-oss numbers got.
"""

import re

import pytest
from botocore.session import Session as BotocoreSession

from app.core.config import settings
from app.kb.chroma_client import get_kb_collection
from app.llm.base import Message
from app.llm.providers.bedrock import BedrockProvider
from app.rag.context_assembler import assemble_context
from app.rag.generation import GENERATION_SYSTEM_PROMPT
from app.rag.pipeline import answer_kb_query
from app.kb.retrieve import retrieve

_aws_credentials_available = BotocoreSession().get_credentials() is not None

pytestmark = pytest.mark.skipif(
    not _aws_credentials_available, reason="No AWS credentials resolvable — real-provider tests are opt-in"
)

CASES = [
    ("How does geofencing work?", "feature_guide"),
    ("What is included in the Enterprise plan?", "pricing"),
    ("How do I register a new GPS device?", "app_faq"),
    ("My GPS device shows offline, what should I do?", "troubleshooting"),
    ("How long is trip and location history retained?", "policy"),
]

# Carried over from the gpt-oss iteration's real, observed typography — not yet confirmed for
# Nova Lite. Kept as a superset check (sentence punctuation OR a closed citation marker) rather
# than removed, since it can only produce false negatives (flagging a genuinely complete Nova
# answer as "possibly truncated"), not false positives that would mask real truncation.
_TRAILING_CITATION = re.compile(r"[\[【]\s*source\s*\d+\s*[\]】]\.?$", re.IGNORECASE)
_CLOSING_QUOTES = "\"'“”‘’"


def _looks_complete(answer: str) -> bool:
    stripped = answer.rstrip()
    if _TRAILING_CITATION.search(stripped):
        return True
    return stripped.rstrip(_CLOSING_QUOTES).endswith((".", "!", "?", ".)"))


def _bedrock() -> BedrockProvider:
    return BedrockProvider(model_id=settings.bedrock_model_id, region=settings.bedrock_region, profile=settings.aws_profile)


@pytest.mark.parametrize("query,category", CASES, ids=[c[1] for c in CASES])
async def test_realistic_rag_answers_are_not_truncated_at_the_configured_cap(query, category):
    llm = _bedrock()
    kb = get_kb_collection()
    result = await answer_kb_query(query, category, llm, collection=kb)
    assert result.llm_invoked, f"{category}: expected a real LLM call, got a fallback response"
    assert _looks_complete(result.answer), (
        f"{category}: answer doesn't end with sentence-ending punctuation or a closed citation "
        f"marker, possible truncation: {result.answer!r}"
    )


async def test_longest_realistic_answer_truncation_rate_stays_within_measured_bounds():
    """The case (TROUBLESHOOTING_DEVICE) that needed the highest max_tokens with the previous
    provider (gpt-oss). Repeats the same real call several times since output length varies run
    to run at temperature=0.2 — a single sample isn't reliable evidence either way.

    Asserts a tolerance, not zero, for the same reason the original Groq/gpt-oss versions of
    this test did: no fixed cap eliminates truncation risk entirely for an open-ended procedural
    answer. This is a regression tripwire against the cap drifting back down or a genuinely
    worse fit for Nova Lite, not a demand for perfection — and per this file's module docstring,
    its own bounds haven't been re-measured against Nova Lite yet either.
    """
    llm = _bedrock()
    kb = get_kb_collection()
    query = "My GPS device shows offline, what should I do?"
    retrieved = retrieve(query, top_k=6, collection=kb)
    context = assemble_context(retrieved, top_n=4)
    prompt = f"Context:\n{context.context_text}\n\nQuestion: {query}"

    samples = 5
    truncated = 0
    for _ in range(samples):
        response = await llm.generate(
            [Message(role="system", content=GENERATION_SYSTEM_PROMPT), Message(role="user", content=prompt)],
            max_tokens=settings.llm_max_tokens,
        )
        # Converse's own shape: top-level "stopReason", not choices[0].finish_reason (the old
        # invoke_model/OpenAI-compatible shape) — "max_tokens" is Converse's truncation value,
        # not "length". Confirmed against Converse's documented response shape.
        if response.raw.get("stopReason") == "max_tokens":
            truncated += 1

    assert truncated <= samples // 2, f"{truncated}/{samples} repeated calls truncated at max_tokens={settings.llm_max_tokens}"
