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

# Single source of truth for the "no LLM available" message — used by both rag_tool_node and
# synthesis_node (app/agent/nodes.py) when generation fails, and by ChatService as the
# graph-level fallback for anything that somehow still escapes both. Keeping the graph-level
# handling as the primary path matters: LLMUnavailableError caught only at the ChatService
# layer (the original design) meant the exception aborted the graph mid-run, skipping
# memory_update_node entirely — so a correctly-resolved vehicle reference was silently lost
# because *phrasing* the answer failed, not because resolution did. Found by actually running
# the server end-to-end with no API key configured, not by inspection.
LLM_UNAVAILABLE_RESPONSE = (
    "I'm unable to generate a full response right now (no AI provider is configured in this "
    "environment). Basic questions that don't need generation — greetings, clarifying "
    "questions — still work."
)


def direct_response(route_outcome: str, final_intent: str) -> str:
    if route_outcome == "BACKLOG_UNSUPPORTED":
        return _BACKLOG_RESPONSE
    if route_outcome == "UNKNOWN_INTENT":
        return _UNKNOWN_INTENT_RESPONSE
    return _META_RESPONSES.get(final_intent, _UNKNOWN_INTENT_RESPONSE)
