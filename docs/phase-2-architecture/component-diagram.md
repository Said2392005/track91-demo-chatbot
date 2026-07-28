# Component Diagram — Phase 2

## Diagram

```mermaid
graph TD
    Client[Client / API Consumer]

    subgraph API["API Layer (Phase 11)"]
        Router[FastAPI Routers<br/>thin: parse to call to return]
        ChatSvc[ChatService]
        AuthMW[Auth + Logging Middleware<br/>injects company_id, session_id, request_id]
    end

    subgraph Agent["Agent Orchestration (Phase 10 — LangGraph)"]
        Graph[Compiled Agent Graph]
        Intent[Intent Classifier node<br/>Phase 6]
        Entity[Entity Extractor +<br/>Coreference Resolver node<br/>Phase 6 / 8]
        RouteNode[Deterministic Router node<br/>Phase 9 — lookup table, no LLM]
        ToolExec[Tool Execution node]
        RAGNode[RAG node<br/>Phase 7]
        Gen[Response Generation node]
    end

    subgraph Tools["Tool / Data-Access Layer"]
        ToolReg[Tool Registry<br/>Phase 9]
        Repos[Mongo Repository Layer<br/>Phase 3<br/>Vehicle/Driver/Trip/Alert/<br/>Maintenance/Geofence repos]
        GPSClient["Fleet GPS Client<br/>(interface; Mock impl for now)<br/>Phase 9"]
    end

    subgraph RAGSub["RAG Subsystem (Phase 4/5/7)"]
        Embed[Embedding Service<br/>self-hosted BGE-M3 /<br/>sentence-transformers]
        Retriever[Retriever + Re-ranker]
        CtxAsm["Context Assembler<br/>(incl. PRICING approved-doc gate)"]
    end

    subgraph LLMLayer["LLM Provider Interface (strategy pattern)"]
        LLMIface[LLMProvider interface]
        DeepSeek[DeepSeek adapter]
        Gemini[Gemini Flash-Lite adapter]
        Other[... other adapters]
    end

    subgraph Memory["Session Memory (Phase 8)"]
        Checkpointer[LangGraph Checkpointer]
        ActiveEntities[Active-Entity Tracker]
    end

    subgraph Stores["Data Stores"]
        Mongo[(MongoDB<br/>history + sessions —<br/>never live telemetry)]
        Chroma[(ChromaDB<br/>KB chunks)]
        FleetAPI[(External Fleet GPS API<br/>mocked in this build)]
    end

    Client --> Router
    Router --> ChatSvc
    AuthMW -.wraps.-> Router
    ChatSvc --> Graph

    Graph --> Intent --> Entity --> RouteNode
    RouteNode -->|LIVE_API / MONGO_REPO intents| ToolExec
    RouteNode -->|RAG intents| RAGNode
    RouteNode -->|NONE / meta intents| Gen

    ToolExec --> ToolReg
    ToolReg --> Repos --> Mongo
    ToolReg --> GPSClient --> FleetAPI

    RAGNode --> Embed
    RAGNode --> Retriever --> Chroma
    RAGNode --> CtxAsm
    CtxAsm --> Gen

    ToolExec --> Gen
    Gen --> LLMIface
    LLMIface --> DeepSeek
    LLMIface --> Gemini
    LLMIface --> Other

    Graph <--> Checkpointer <--> Mongo
    Entity <--> ActiveEntities
    ActiveEntities <--> Checkpointer

    Gen --> ChatSvc --> Router --> Client
```

## Component responsibilities

| Component | Owning phase | Responsibility | Must NOT do |
|---|---|---|---|
| FastAPI Routers | 11 | Parse HTTP request → call `ChatService` → serialize response | Contain business logic, call repositories/LLM directly |
| Auth + Logging Middleware | 11 | Resolve `company_id` from auth, generate/propagate `request_id`, attach `session_id` | Be bypassable — every route passes through it |
| ChatService | 11 | One turn's orchestration: load/save session, invoke agent graph, map to response DTO | Contain intent/routing logic (that's the graph's job) |
| Agent Graph (LangGraph) | 10 | Sequence the nodes below per turn; own the state schema | Import FastAPI types |
| Intent Classifier node | 6 | Map utterance (+ session state) → one intent from the Phase 1 taxonomy | Decide which tool/subsystem to call |
| Entity Extractor / Coreference node | 6, 8 | Extract raw entity spans, normalize (e.g. `vehicle_ref` canonicalization), resolve pronouns via active-entity tracker | Resolve to Mongo IDs itself without a repository lookup |
| Deterministic Router node | 9 | Pure lookup: intent → {subsystem, tool/handler, required entities, gate fn} | Call an LLM to decide routing |
| Tool Execution node | 9/10 | Invoke the resolved tool via the Tool Registry, handle missing-entity/backlog-intent rejection | Talk to Mongo/Fleet API directly (must go through registry → repo/client) |
| Tool Registry | 9 | Maps tool name → callable backed by exactly one repository or the GPS client | Contain routing decisions (that's the Router node) |
| Mongo Repository Layer | 3 | One repository per collection; every method requires `company_id`; only code that imports `motor` | Be called from routers/nodes without going through the registry/service |
| Fleet GPS Client | 9 (mocked) | Interface for live telemetry; `MockFleetGPSProvider` today, real adapter later | Persist any data it returns |
| RAG node / Embedding / Retriever / Context Assembler | 4, 5, 7 | Embed query → retrieve + re-rank chunks → assemble cited context, enforcing the `PRICING` approved-doc gate | Let ungated/unapproved chunks answer `PRICING` |
| LLMProvider interface + adapters | cross-cutting | Single `generate()` contract; concrete SDK calls isolated to adapter modules | Be imported directly by any node other than Response Generation (and Context Assembler for citation formatting) |
| Session Memory (Checkpointer + Active-Entity Tracker) | 8 | Persist per-`session_id` conversation/graph state and last-referenced entities in Mongo | Store live telemetry; leak across sessions/tenants |
| MongoDB | 3, 8 | History collections + session/checkpoint collection | Store live GPS/speed/fuel/health data |
| ChromaDB | 5 | KB chunk vectors, ingested offline, idempotent upsert | Store live or transactional data |

## Notes

- The Router node is the only place `target_subsystem` (from the Phase 1 intent taxonomy) is
  interpreted. Everything downstream just executes what it's told.
- `Gen` (Response Generation) is reached from three different paths — tool result, RAG context,
  or directly from meta/`NONE` intents — but always through the same `LLMProvider` interface, so
  provider swapping is a single config change regardless of which path produced the input.
