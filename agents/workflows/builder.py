"""Workflow builder — dynamic LangGraph construction from YAML templates.

AGENTS.md §1.2: 严禁在 report_workflow.py 中硬编码节点顺序。
Must use this builder + config/workflow_templates.yaml for dynamic assembly.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Type

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)


class WorkflowBuilder:
    """Builds a compiled LangGraph StateGraph from YAML template config.

    Usage:
        builder = WorkflowBuilder()
        graph = builder.build("deep_report", ReportState)
        result = await graph.ainvoke(initial_state)
    """

    def __init__(self) -> None:
        from agents.workflows.templates.loader import template_loader
        self._loader = template_loader

    def build(
        self,
        template_name: str,
        state_schema: Type,
    ) -> StateGraph:
        """Build and compile a LangGraph from a named template.

        Args:
            template_name: Template name (deep_report / flash_news / earnings_analysis).
            state_schema: TypedDict subclass for the graph state.

        Returns:
            Compiled StateGraph ready for execution.

        Raises:
            ValueError: If template is invalid or nodes are missing.
        """
        tpl = self._loader.get_template(template_name)

        graph = StateGraph(state_schema)

        # ── Register nodes ────────────────────────────────────────────
        for node_name in tpl.get("nodes", []):
            entry_func = self._load_node_entry(node_name)
            graph.add_node(node_name, entry_func)

        # ── Add linear edges ──────────────────────────────────────────
        edges = tpl.get("edges", {})
        for pair in edges.get("linear", []):
            if len(pair) == 2:
                graph.add_edge(pair[0], pair[1])

        # ── Add conditional edges ─────────────────────────────────────
        for cond_edge in edges.get("conditional", []):
            from_node = cond_edge["from"]
            routes = cond_edge.get("routes", {})
            if routes:
                router = self._build_router(from_node, routes)
                # Collect all destination nodes
                destinations: set[str] = set()
                for v in routes.values():
                    if isinstance(v, str):
                        destinations.add(v)
                    elif isinstance(v, dict):
                        destinations.add(v.get("true_dest", ""))
                        destinations.add(v.get("false_dest", ""))
                graph.add_conditional_edges(from_node, router, destinations - {""})

        # ── Set entry and finish ──────────────────────────────────────
        entry = tpl.get("entry_point", "intent_classifier")
        graph.set_entry_point(entry)

        finish = tpl.get("finish_point", "")
        if finish:
            graph.add_edge(finish, END)

        compiled = graph.compile()
        logger.info(
            "Built workflow '%s': %d nodes, entry=%s",
            template_name,
            len(tpl.get("nodes", [])),
            entry,
        )
        return compiled

    def _load_node_entry(self, node_name: str) -> Any:
        """Dynamically import a node module's ``entry`` function."""
        module_path = f"agents.nodes.{node_name}"
        try:
            module = importlib.import_module(module_path)
            return getattr(module, "entry")
        except (ImportError, AttributeError) as exc:
            raise ValueError(
                f"Node '{node_name}' not found. Expected {module_path}.entry(). "
                f"Error: {exc}"
            ) from exc

    def _build_router(self, from_node: str, routes: dict[str, Any]) -> Any:
        """Build a routing function for conditional edges."""
        from agents.edges.conditional_edges import make_router

        return make_router(from_node, routes)
