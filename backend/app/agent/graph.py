"""Compiled LangGraph workflow. Built once; invoked per request with a DB session in config."""

from __future__ import annotations

from app.agent import compat as _langgraph_compat  # noqa: F401  — must precede langgraph import

from langgraph.graph import END, START, StateGraph

from app.agent import nodes, routing
from app.agent.state import AgentState

_compiled = None


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("classify_intent", nodes.classify_intent)
    graph.add_node("rewrite_query", nodes.rewrite_query)
    graph.add_node("retrieve_knowledge", nodes.retrieve_knowledge)
    graph.add_node("generate_answer", nodes.generate_answer)
    graph.add_node("clarify", nodes.clarify)
    graph.add_node("handle_unsupported", nodes.handle_unsupported)
    graph.add_node("route_contact", nodes.route_contact)

    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        routing.after_intent,
        {
            "rewrite_query": "rewrite_query",
            "route_contact": "route_contact",
            "handle_unsupported": "handle_unsupported",
        },
    )
    graph.add_edge("rewrite_query", "retrieve_knowledge")
    graph.add_conditional_edges(
        "retrieve_knowledge",
        routing.after_evidence,
        {
            "generate_answer": "generate_answer",
            "clarify": "clarify",
        },
    )
    graph.add_edge("generate_answer", END)
    graph.add_edge("clarify", END)
    graph.add_edge("handle_unsupported", END)
    graph.add_edge("route_contact", END)
    return graph.compile()


def get_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled
