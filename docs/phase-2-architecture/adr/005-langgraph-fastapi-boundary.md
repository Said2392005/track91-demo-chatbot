# ADR 005: LangGraph Boundary Relative to FastAPI

## Status

Accepted

## Context

FastAPI's request/response cycle is stateless per call, but a conversation needs state
(dialogue history, active entities) to persist across turns, and LangGraph is the chosen agent
framework for sequencing classification → routing → tool/RAG → generation. We need a clear seam
between "HTTP layer" and "stateful agent" so neither leaks into the other.

## Decision

FastAPI routers/services treat the compiled LangGraph graph as a single injected dependency.
Each HTTP request invokes it once: `graph.ainvoke(input, config={"configurable": {"thread_id":
session_id}})`. LangGraph's own checkpointer (Phase 8, backed by MongoDB via the repository
layer — see [[001-repository-pattern-for-mongo]]) persists graph state between calls, keyed by
`session_id`. FastAPI itself remains stateless: no in-process session dict, no sticky-session
assumption. The graph module never imports FastAPI types (`Request`, `Response`, etc.); the
router/service layer never imports individual node internals — only the compiled graph object
and its typed input/output schema.

## Consequences

- The graph is runnable and testable independent of the HTTP layer — Phase 10's node/integration
  tests and Phase 12's eval harness invoke it directly, without spinning up FastAPI.
- Horizontal scaling of the API layer is safe by construction: any instance can handle any
  request for a given `session_id` because state lives in Mongo, not in process memory —
  relevant even at pilot scale since it avoids a rewrite later.
- The router stays thin (per the roadmap's rule): its only job re: the agent is to call
  `ainvoke` and translate the result to a response DTO.
