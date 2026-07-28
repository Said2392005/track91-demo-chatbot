"""Fixed direct-response templates for outcomes that need no tool and no LLM call: meta
intents (NO_TOOL), backlog-unsupported intents, and the (should-not-happen-given-a-fixed-
taxonomy) unknown-intent fallback."""

_META_RESPONSES = {
    "GREETING": "Hello! How can I help you with your fleet today?",
    "GOODBYE": "Goodbye! Let me know if you need anything else.",
    "CHITCHAT": (
        "I'm here to help with your fleet — vehicle tracking, trips, alerts, maintenance, "
        "and more. What would you like to know?"
    ),
    "OUT_OF_SCOPE": (
        "I'm focused on helping with your Track91 fleet — I can't help with that, but I'm "
        "happy to help with vehicles, trips, alerts, maintenance, or your account."
    ),
    # AFFIRM_DENY on its own, without the multi-turn disambiguation flow (tracking which
    # candidate a prior CLARIFICATION_NEEDED turn offered) to resolve against, has nothing
    # concrete to confirm/deny yet — that flow is not built in this phase. Flagged limitation,
    # not silently pretended to work: see docs/phase-10-agent-workflow/agent-workflow.md.
    "AFFIRM_DENY": "Got it — could you tell me again what you'd like to know?",
}

_BACKLOG_RESPONSE = "That's not supported through chat yet — please use the Track91 dashboard for this."
_UNKNOWN_INTENT_RESPONSE = "Sorry, I didn't quite understand that — could you rephrase?"


def direct_response(route_outcome: str, final_intent: str) -> str:
    if route_outcome == "BACKLOG_UNSUPPORTED":
        return _BACKLOG_RESPONSE
    if route_outcome == "UNKNOWN_INTENT":
        return _UNKNOWN_INTENT_RESPONSE
    return _META_RESPONSES.get(final_intent, _UNKNOWN_INTENT_RESPONSE)
