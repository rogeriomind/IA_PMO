from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agent.domains.projects.nodes import ProjectNodes
from app.agent.state import AgentState


def build_project_subgraph(nodes: ProjectNodes):
    graph = StateGraph(AgentState)
    graph.add_node("resolve_project", nodes.resolve_project)
    graph.add_node("select_project_tool", nodes.select_project_tool)
    graph.add_node("execute_tool", nodes.execute_tool)
    graph.add_node("normalize_project_data", nodes.normalize_project_data)
    graph.add_node("generate_executive_summary", nodes.generate_executive_summary)
    graph.set_entry_point("resolve_project")
    graph.add_edge("resolve_project", "select_project_tool")
    graph.add_edge("select_project_tool", "execute_tool")
    graph.add_edge("execute_tool", "normalize_project_data")
    graph.add_edge("normalize_project_data", "generate_executive_summary")
    graph.add_edge("generate_executive_summary", END)
    return graph.compile()

