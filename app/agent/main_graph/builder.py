from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agent.main_graph.nodes import PMOMainGraphNodes
from app.agent.main_graph.state import PMOAgentState


def build_pmo_agent_graph(nodes: PMOMainGraphNodes):
    graph = StateGraph(PMOAgentState)
    graph.add_node("validate_event", nodes.validate_event)
    graph.add_node("load_identity", nodes.load_identity)
    graph.add_node("load_thread_memory", nodes.load_thread_memory)
    graph.add_node("normalize_event", nodes.normalize_event)
    graph.add_node("handle_global_commands", nodes.handle_global_commands)
    graph.add_node("resolve_current_flow", nodes.resolve_current_flow)
    graph.add_node("route_to_subgraph", nodes.route_to_subgraph)
    graph.add_node("persist_session_summary", nodes.persist_session_summary)
    graph.add_node("build_api_response", nodes.build_api_response)

    graph.set_entry_point("validate_event")
    graph.add_edge("validate_event", "load_identity")
    graph.add_edge("load_identity", "load_thread_memory")
    graph.add_edge("load_thread_memory", "normalize_event")
    graph.add_edge("normalize_event", "handle_global_commands")
    graph.add_edge("handle_global_commands", "resolve_current_flow")
    graph.add_edge("resolve_current_flow", "route_to_subgraph")
    graph.add_edge("route_to_subgraph", "persist_session_summary")
    graph.add_edge("persist_session_summary", "build_api_response")
    graph.add_edge("build_api_response", END)
    return graph.compile()
