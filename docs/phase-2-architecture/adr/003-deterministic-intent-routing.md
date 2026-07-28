# ADR 003: Deterministic Intent-to-Tool Routing

## Status

Accepted

## Context

The working agreement requires that intent → tool routing never be an LLM guess: the LLM
phrases answers but must never decide which system of record (live API, Mongo, KB) to hit.
This needs to be true structurally, not just as a convention agent nodes are expected to
follow.

## Decision

The Phase 9 Router node is plain code: a lookup table/dict keyed by the fixed intent set from
the Phase 1 taxonomy, mapping each intent to `{target_subsystem, tool_name, required_entities,
gate_fn?}` (`gate_fn` covers cases like the `PRICING` approved-doc check). It runs *after*
intent classification and entity resolution (Phase 6) and *before* any tool execution or RAG
call. No LLM call happens inside this node. If the classifier returns an intent not present in
the table, or required entities are missing, the router returns a defined outcome
(`CLARIFICATION_NEEDED` or a rejection for backlog intents) rather than falling through to
undefined behavior.

## Consequences

- The router is 100% table-driven-testable: (intent, entities, memory-state) → (tool called,
  params passed), per the Phase 9 testing plan.
- Adding a new intent requires an explicit routing-table entry — there is no path for a new
  intent to "just work" via LLM improvisation.
- Backlog intents (Phase 1, section C) have a defined rejection behavior today instead of
  silently doing nothing or being mis-routed.
- This node is the single enforcement point referenced by [[001-repository-pattern-for-mongo]]
  and the Fleet GPS client boundary — it decides *which* tool runs, but never executes Mongo/API
  calls itself.
