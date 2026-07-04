from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.graph.nodes import AgentGraphNodes
from app.graph.state import AgentState


def build_invoke_graph(nodes: AgentGraphNodes):
    graph = StateGraph(AgentState)

    graph.add_node("load_context", nodes.load_context)
    graph.add_node("classify_intent", nodes.classify_intent)
    graph.add_node("route_by_intent", nodes.route_by_intent)
    graph.add_node("call_mcp_read_tool", nodes.call_mcp_read_tool)
    graph.add_node("extract_entities", nodes.extract_entities)
    graph.add_node("validate_required_fields", nodes.validate_required_fields)
    graph.add_node("prepare_pending_action", nodes.prepare_pending_action)
    graph.add_node("ask_confirmation", nodes.ask_confirmation)
    graph.add_node("generate_response", nodes.generate_response)

    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "classify_intent")
    graph.add_edge("classify_intent", "route_by_intent")
    graph.add_conditional_edges(
        "route_by_intent",
        lambda state: state.get("route", "respond"),
        {
            "read": "call_mcp_read_tool",
            "write": "extract_entities",
            "respond": "generate_response",
        },
    )
    graph.add_edge("call_mcp_read_tool", "generate_response")
    graph.add_edge("extract_entities", "validate_required_fields")
    graph.add_edge("validate_required_fields", "prepare_pending_action")
    graph.add_edge("prepare_pending_action", "ask_confirmation")
    graph.add_edge("ask_confirmation", "generate_response")
    graph.add_edge("generate_response", END)

    return graph.compile()


def build_confirmation_graph(nodes: AgentGraphNodes):
    graph = StateGraph(AgentState)

    graph.add_node("load_pending_action", nodes.load_pending_action)
    graph.add_node("execute_mcp_write_tool", nodes.execute_mcp_write_tool)
    graph.add_node("generate_response", nodes.generate_confirmation_response)

    graph.set_entry_point("load_pending_action")
    graph.add_edge("load_pending_action", "execute_mcp_write_tool")
    graph.add_edge("execute_mcp_write_tool", "generate_response")
    graph.add_edge("generate_response", END)

    return graph.compile()

