# Sequence Diagrams — Phase 2

Three representative flows, one per `target_subsystem` shape from the Phase 1 intent taxonomy.
A fourth diagram shows the `PRICING` gate branch in detail since it has non-obvious control flow.

**Locked-in rule:** vehicle registration normalization (the strip/uppercase/de-separate/
regex-validate pipeline defined in `entity-taxonomy.md`) happens exactly once per turn, inside
the Entity Extractor node, before the Deterministic Router node ever runs. The Router, Tool
Registry, repositories, and Fleet GPS client only ever see a canonical `vehicle_id` (or the
already-normalized plate used to resolve it) — never a raw user-typed span. Diagrams 1 and 2
both show this explicitly for that reason, rather than one showing it and the other skipping to
the resolved ID.

## 1. `LIVE_API` flow — `GET_VEHICLE_SPEED`

_"What's MH12AB1234's speed?"_

```mermaid
sequenceDiagram
    participant U as User
    participant R as FastAPI Router
    participant CS as ChatService
    participant G as Agent Graph
    participant IC as Intent Classifier
    participant EE as Entity Extractor
    participant RT as Deterministic Router
    participant TR as Tool Registry
    participant GPS as Fleet GPS Client (mock)
    participant LLM as LLMProvider

    U->>R: POST /chat {message, session_id}
    R->>CS: handle(message, session_id, company_id)
    CS->>G: ainvoke(state, thread_id=session_id)
    G->>IC: classify(utterance, session_state)
    IC-->>G: intent = GET_VEHICLE_SPEED
    G->>EE: extract_and_resolve(utterance, session_state)
    Note over EE: normalization (entity-taxonomy.md rule):<br/>"MH12AB1234" → strip/uppercase/de-separate → canonical plate<br/>→ roster lookup (company_id-scoped) → vehicle_id<br/>happens ONCE here — RT never sees a raw span
    EE-->>G: entities = {vehicle_id: "veh_123"}
    G->>RT: route(intent, entities)
    RT-->>G: {subsystem: LIVE_API, tool: get_vehicle_speed}
    G->>TR: execute(get_vehicle_speed, vehicle_id, company_id)
    TR->>GPS: get_speed(vehicle_id)
    GPS-->>TR: {speed_kmph: 42, ts: ...}
    Note over TR,GPS: never written to Mongo or Chroma
    TR-->>G: tool_result
    G->>LLM: generate(tool_result, utterance)
    LLM-->>G: "MH12AB1234 is currently going 42 km/h."
    G-->>CS: response + updated session state (active vehicle = veh_123)
    CS-->>R: ChatResponse DTO
    R-->>U: 200 OK
```

## 2. `MONGO_REPO` flow — `GET_TRIP_HISTORY`

_"Show MH12AB1234's trips yesterday"_ — then a follow-up _"what about its alerts?"_ to show
coreference resolution against session memory.

```mermaid
sequenceDiagram
    participant U as User
    participant G as Agent Graph
    participant IC as Intent Classifier
    participant EE as Entity Extractor
    participant AT as Active-Entity Tracker
    participant RT as Deterministic Router
    participant TR as Tool Registry
    participant TripRepo as TripRepository
    participant Mongo as MongoDB

    U->>G: "Show MH12AB1234's trips yesterday"
    G->>IC: classify(...)
    IC-->>G: intent = GET_TRIP_HISTORY
    G->>EE: extract_and_resolve(...)
    Note over EE: normalization (entity-taxonomy.md rule):<br/>"MH12AB1234" → strip/uppercase/de-separate → canonical plate<br/>→ roster lookup (company_id-scoped) → vehicle_id<br/>happens ONCE here — RT never sees a raw span
    EE-->>G: entities = {vehicle_id: "veh_123", date_range: [2026-07-27, 2026-07-27]}
    G->>AT: set_active(vehicle_id="veh_123")
    G->>RT: route(intent, entities)
    RT-->>G: {subsystem: MONGO_REPO, tool: get_trip_history}
    G->>TR: execute(get_trip_history, vehicle_id, date_range, company_id)
    TR->>TripRepo: find_trips(company_id, vehicle_id, date_range)
    Note over TripRepo,Mongo: filter always AND-ed with company_id
    TripRepo->>Mongo: query (compound index: company_id, vehicle_id, date)
    Mongo-->>TripRepo: trip docs
    TripRepo-->>TR: trips
    TR-->>G: tool_result
    G-->>U: (via Gen) "MH12AB1234 made 3 trips yesterday: ..."

    U->>G: "What about its alerts?"
    G->>IC: classify(...)
    IC-->>G: intent = GET_ALERT_HISTORY
    G->>EE: extract_and_resolve(...)
    Note over EE,AT: "its" has no explicit vehicle_ref span —<br/>pronoun_ref resolves via Active-Entity Tracker
    EE->>AT: resolve_pronoun("its")
    AT-->>EE: vehicle_id = "veh_123"
    EE-->>G: entities = {vehicle_id: "veh_123", date_range: [today]}
    G->>RT: route(intent, entities)
    RT-->>G: {subsystem: MONGO_REPO, tool: get_alert_history}
    G->>TR: execute(get_alert_history, vehicle_id, date_range, company_id)
    TR-->>G: tool_result
    G-->>U: (via Gen) "No alerts for MH12AB1234 today."
```

## 3. `RAG` flow — `EXPLAIN_FEATURE`

_"How does geofencing work?"_

```mermaid
sequenceDiagram
    participant U as User
    participant G as Agent Graph
    participant IC as Intent Classifier
    participant RT as Deterministic Router
    participant RAG as RAG Node
    participant Embed as Embedding Service
    participant Chroma as ChromaDB
    participant Rerank as Re-ranker
    participant CtxAsm as Context Assembler
    participant LLM as LLMProvider

    U->>G: "How does geofencing work?"
    G->>IC: classify(...)
    IC-->>G: intent = EXPLAIN_FEATURE, kb_topic = "geofencing"
    G->>RT: route(intent, entities)
    RT-->>G: {subsystem: RAG, tool: kb_retrieve}
    G->>RAG: retrieve_and_answer(kb_topic="geofencing")
    RAG->>Embed: embed("geofencing")
    Embed-->>RAG: query_vector
    RAG->>Chroma: query(query_vector, top_k)
    Chroma-->>RAG: candidate chunks
    RAG->>Rerank: rerank(candidate chunks, query)
    Rerank-->>RAG: top_n chunks
    RAG->>CtxAsm: assemble(top_n chunks)
    CtxAsm-->>RAG: cited context block
    RAG->>LLM: generate(context, query)
    LLM-->>RAG: cited answer
    RAG-->>G: response
    G-->>U: "Geofencing lets you draw a virtual boundary... [source: KB doc #12]"
```

## 4. `PRICING` gate branch (detail)

_"How much does the Pro plan cost?"_ — shown separately because the gate's alt path
(no approved doc → canned response) is easy to lose in a happy-path-only diagram.

```mermaid
sequenceDiagram
    participant U as User
    participant RAG as RAG Node
    participant Chroma as ChromaDB
    participant CtxAsm as Context Assembler
    participant LLM as LLMProvider

    U->>RAG: retrieve_and_answer(intent=PRICING, kb_topic="Pro plan cost")
    RAG->>Chroma: query(embedding of "Pro plan cost")
    Chroma-->>RAG: candidate chunks

    alt An approved-pricing-flagged chunk is retrieved
        RAG->>CtxAsm: assemble(chunks) — includes source.approved_pricing=true chunk
        CtxAsm-->>RAG: cited context
        RAG->>LLM: generate(context, query)
        LLM-->>RAG: answer with cited price
        RAG-->>U: "The Pro plan is ₹X/vehicle/month. [source: Pricing Sheet v3]"
    else No approved-pricing-flagged chunk retrieved
        Note over RAG,CtxAsm: gate check fails — this is a fixed code branch,<br/>not an LLM decision
        RAG-->>U: "I don't have current pricing details — please contact our sales team at ..."
        Note over LLM: LLMProvider is never called with unapproved<br/>context for a PRICING-shaped query
    end
```
