from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agent.graph.nodes import MainGraphNodes
from app.agent.state import AgentState


def build_main_agent_graph(
    *,
    nodes: MainGraphNodes,
    task_query_subgraph,
    task_write_subgraph,
    project_subgraph,
):
    graph = StateGraph(AgentState)

    graph.add_node("load_context", nodes.load_context)
    graph.add_node("authenticate_and_authorize", nodes.authenticate_and_authorize)
    graph.add_node("normalize_message", nodes.normalize_message)
    graph.add_node("deterministic_router", nodes.deterministic_router)
    graph.add_node("classify_and_extract", nodes.classify_and_extract)
    graph.add_node("validate_classification", nodes.validate_classification)
    graph.add_node("route_intent", nodes.route_intent)
    graph.add_node("task_query_subgraph", task_query_subgraph)
    graph.add_node("task_write_subgraph", task_write_subgraph)
    graph.add_node("project_subgraph", project_subgraph)
    graph.add_node("help_or_unknown", nodes.help_or_unknown)
    graph.add_node("validate_tool_result", nodes.validate_tool_result)
    graph.add_node("format_response", nodes.format_response)
    graph.add_node("persist_execution_metadata", nodes.persist_execution_metadata)

    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "authenticate_and_authorize")
    graph.add_edge("authenticate_and_authorize", "normalize_message")
    graph.add_edge("normalize_message", "deterministic_router")
    graph.add_edge("deterministic_router", "classify_and_extract")
    graph.add_edge("classify_and_extract", "validate_classification")
    graph.add_edge("validate_classification", "route_intent")
    graph.add_conditional_edges(
        "route_intent",
        lambda state: state.get("route", "respond"),
        {
            "task_query": "task_query_subgraph",
            "task_write": "task_write_subgraph",
            "project": "project_subgraph",
            "respond": "help_or_unknown",
        },
    )
    graph.add_edge("task_query_subgraph", "validate_tool_result")
    graph.add_edge("task_write_subgraph", "validate_tool_result")
    graph.add_edge("project_subgraph", "validate_tool_result")
    graph.add_edge("help_or_unknown", "validate_tool_result")
    graph.add_edge("validate_tool_result", "format_response")
    graph.add_edge("format_response", "persist_execution_metadata")
    graph.add_edge("persist_execution_metadata", END)
    return graph.compile()

