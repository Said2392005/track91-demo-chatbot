"""
Assembles the LangGraph graph from Phases 6-9 + this phase's node wrappers. Pure assembly, per
the roadmap: entry -> semantic_analysis -> router, conditional edges to
clarify/gps_tool/mongo_tool/rag_tool, all converging on synthesis -> memory_update -> end.

Dependencies (db, llm, gps_client, kb_collection, session_repo, classifier) are bound into each
node via closures at build time (app/agent/nodes.py's make_*_node factories) rather than
threaded through graph state or LangGraph's `configurable` — they're process-lifetime
singletons in this build (Phase 11 will own their construction/DI), and none of them are
themselves checkpoint-serializable (a Motor database, an LLM client, etc. have no business
being persisted as conversation state).
"""

from langgraph.graph import END, START, StateGraph

from app.agent import nodes
from app.agent.state import AgentState


def build_graph(*, classifier, db, llm, gps_client, kb_collection, session_repo, checkpointer=None):
    graph = StateGraph(AgentState)

    graph.add_node("entry", nodes.make_entry_node(session_repo))
    graph.add_node("semantic_analysis", nodes.make_semantic_analysis_node(classifier, db))
    graph.add_node("router", nodes.make_router_node())
    graph.add_node("clarify", nodes.make_clarify_node(session_repo))
    # Each tool node factory now receives ALL FOUR deps, not just the one its own primary
    # subsystem needs — dual-intent handling (app/agent/nodes.py's _execute_secondary_tool)
    # means whichever primary node runs may also need to execute a SECONDARY tool from a
    # different subsystem (e.g. a MONGO_REPO primary + a LIVE_API secondary).
    graph.add_node("gps_tool", nodes.make_gps_tool_node(gps_client, db=db, llm=llm, kb_collection=kb_collection))
    graph.add_node("mongo_tool", nodes.make_mongo_tool_node(db, gps_client=gps_client, llm=llm, kb_collection=kb_collection))
    graph.add_node("rag_tool", nodes.make_rag_tool_node(llm, kb_collection, db=db, gps_client=gps_client))
    graph.add_node("synthesis", nodes.make_synthesis_node(llm))
    graph.add_node("memory_update", nodes.make_memory_update_node(session_repo))

    graph.add_edge(START, "entry")
    graph.add_edge("entry", "semantic_analysis")
    graph.add_edge("semantic_analysis", "router")
    graph.add_conditional_edges(
        "router",
        nodes.route_condition,
        {
            "clarify": "clarify",
            "gps_tool": "gps_tool",
            "mongo_tool": "mongo_tool",
            "rag_tool": "rag_tool",
            "synthesis": "synthesis",
        },
    )
    graph.add_edge("clarify", "synthesis")
    graph.add_edge("gps_tool", "synthesis")
    graph.add_edge("mongo_tool", "synthesis")
    graph.add_edge("rag_tool", "synthesis")
    graph.add_edge("synthesis", "memory_update")
    graph.add_edge("memory_update", END)

    return graph.compile(checkpointer=checkpointer)
