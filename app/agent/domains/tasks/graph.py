from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agent.domains.tasks.nodes import TaskQueryNodes, TaskWriteNodes
from app.agent.state import AgentState


def build_task_query_subgraph(nodes: TaskQueryNodes):
    graph = StateGraph(AgentState)
    graph.add_node("validate_query", nodes.validate_query)
    graph.add_node("resolve_parameters", nodes.resolve_parameters)
    graph.add_node("select_read_tool", nodes.select_read_tool)
    graph.add_node("execute_tool", nodes.execute_tool)
    graph.add_node("normalize_result", nodes.normalize_result)
    graph.add_node("format_domain_result", nodes.format_domain_result)
    graph.set_entry_point("validate_query")
    graph.add_edge("validate_query", "resolve_parameters")
    graph.add_edge("resolve_parameters", "select_read_tool")
    graph.add_edge("select_read_tool", "execute_tool")
    graph.add_edge("execute_tool", "normalize_result")
    graph.add_edge("normalize_result", "format_domain_result")
    graph.add_edge("format_domain_result", END)
    return graph.compile()


def build_task_write_subgraph(nodes: TaskWriteNodes):
    graph = StateGraph(AgentState)
    graph.add_node("extract_write_parameters", nodes.extract_write_parameters)
    graph.add_node("validate_required_fields", nodes.validate_required_fields)
    graph.add_node("validate_business_rules", nodes.validate_business_rules)
    graph.add_node("load_current_task", nodes.load_current_task)
    graph.add_node("build_action_preview", nodes.build_action_preview)
    graph.add_node("interrupt_for_confirmation", nodes.interrupt_for_confirmation)
    graph.add_node("execute_write_tool", nodes.execute_write_tool)
    graph.add_node("read_after_write", nodes.read_after_write)
    graph.add_node("validate_final_state", nodes.validate_final_state)
    graph.add_node("format_domain_result", nodes.format_domain_result)
    graph.set_entry_point("extract_write_parameters")
    graph.add_edge("extract_write_parameters", "validate_required_fields")
    graph.add_edge("validate_required_fields", "validate_business_rules")
    graph.add_edge("validate_business_rules", "load_current_task")
    graph.add_edge("load_current_task", "build_action_preview")
    graph.add_edge("build_action_preview", "interrupt_for_confirmation")
    graph.add_edge("interrupt_for_confirmation", "execute_write_tool")
    graph.add_edge("execute_write_tool", "read_after_write")
    graph.add_edge("read_after_write", "validate_final_state")
    graph.add_edge("validate_final_state", "format_domain_result")
    graph.add_edge("format_domain_result", END)
    return graph.compile()

