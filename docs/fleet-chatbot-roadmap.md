# Fleet Chatbot — Implementation Roadmap & Working Agreement

This is the reference copy of the approved roadmap and design rules. Every phase should be
checked against this file before starting and before merging.


## Environment assumptions (confirmed at Phase 1 kickoff)

- **Fleet GPS API**: not yet available. Build a mock provider behind the same interface the
  real API will later implement, so swapping in the real API is a config/adapter change only.
- **Domain data (Mongo seed data + KB documents)**: none available yet. All seed data and
  knowledge-base source documents are synthetic/fabricated for development, clearly marked as
  such.
- **Scale target**: small pilot, <50 concurrent users. Optimize for correctness and clean
  layering over throughput; no sharding/caching architecture required yet.


## Phase order (do not skip or merge)

1. Project Planning — intent taxonomy, entity taxonomy, non-goals doc
2. System Architecture — component diagram, sequence diagram, layering ADRs
3. MongoDB Schema & Indexes — collections, seed data, schema validation tests
4. Knowledge Base Design — chunking strategy, metadata schema, source inventory
5. Embedding Pipeline — PDF/doc → chunks → ChromaDB, idempotent ingestion
6. Semantic Analysis — intent classifier, entity extractor, coreference resolution
7. RAG Pipeline — retrieval, re-ranking, context assembly, cited generation
8. Conversation Memory — session store, active-entity tracking, LangGraph checkpointer
9. API Tool Calling — deterministic intent-to-tool router, tool registry
10. Agent Workflow — LangGraph graph: nodes, conditional routing, state schema
11. FastAPI Backend — routers, services, repositories, DI, config, logging, auth
12. Testing — unit, integration, API, load test, AI eval golden-set harness
13. Deployment — Dockerfiles, docker-compose, CI/CD, env config, docs


## Tech stack (fixed)

- Backend: Python, FastAPI
- Database: MongoDB (via `motor`, async)
- Vector DB: ChromaDB
- Agent framework: LangGraph
- Embeddings: BGE-M3 or sentence-transformers, self-hosted (no external embedding API)
- LLM: swappable behind one provider-agnostic interface; default to a cheap model
  (DeepSeek / Gemini Flash-Lite) for dev
- Deployment: Docker Compose locally; no AWS-specific code until Phase 13+


## Non-negotiable design rules

- Intent → tool routing is a **deterministic lookup table**, never an LLM guess. The LLM only
  phrases the final answer.
- Live GPS data (location, speed, fuel, live health) is **never stored** in Mongo or Chroma —
  always fetched live through a service layer. Mongo stores history (trips, alerts,
  maintenance) only.
- LLM client sits behind one interface (strategy pattern) — swapping providers is a config
  change, not a code change.
- All Mongo access goes through a repository layer — no raw `pymongo`/`motor` calls from
  services, agent nodes, or routers.
- Every Mongo query is scoped by `company_id` — enforced at the repository layer, not
  per-endpoint.
- ChromaDB ingestion is idempotent (stable chunk IDs, upsert not insert).
- Routers stay thin: parse request → call service → return response.
- Structured (JSON) logging with `session_id`/`request_id` correlation from Phase 11 onward.


## Per-phase testing expectations

| Phase | Tests required |
|---|---|
| 3 | Schema validation + index existence tests |
| 5 | Idempotency test + retrieval smoke test against a small golden set |
| 6 | Intent classifier unit tests (5+ paraphrases/intent) + entity extraction on malformed/partial input |
| 7 | Retrieval precision@k on the golden set |
| 8 | Scripted pronoun-resolution test (e.g. "MH12AB1234" → later "its speed" resolves correctly) |
| 9 | Table-driven tests: (intent, entities, memory-state) → (tool called, params passed) |
| 10 | Node-level unit tests + 2-3 full multi-turn integration tests |
| 11 | Contract tests per router, DI override tests |
| 12 | Full pyramid + load test + AI eval harness (40-60 Q&A golden set: intent accuracy, entity accuracy, retrieval precision, answer faithfulness) |
| 13 | CI pipeline runs the above on every PR |


## End-of-phase checklist

1. Restate objective/deliverables before starting.
2. Confirm dependency on previous phase's output.
3. Show folder structure diff after finishing.
4. Run and show test output.
5. Propose a commit message (`feat(scope): summary`).
6. **Stop and wait for go-ahead** — never auto-continue to the next phase.
