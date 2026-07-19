"""Workflow builder — dynamic LangGraph construction from YAML templates.

AGENTS.md §1.2: 严禁在 report_workflow.py 中硬编码节点顺序。
Must use this builder + config/workflow_templates.yaml for dynamic assembly.
"""

from __future__ import annotations

import functools
import importlib
import logging
import time
from typing import Any, Type

from langgraph.graph import END, StateGraph

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
        harness_orchestrator: object | None = None,
        checkpointer: object | None = None,
    ) -> StateGraph:
        """Build and compile a LangGraph from a named template.

        Args:
            template_name: Template name (deep_report / flash_news / earnings_analysis).
            state_schema: TypedDict subclass for the graph state.
            harness_orchestrator: Optional HarnessOrchestrator instance.
                When provided, each node entry function is wrapped with
                governance checks (input safety, permission, structural,
                fact verification, hallucination, audit).
            checkpointer: Optional AsyncPostgresSaver instance.
                When provided, state is persisted to PostgreSQL via
                LangGraph Checkpointer (enables interrupt/resume).

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
            if harness_orchestrator is not None:
                entry_func = self._wrap_node_with_harness(
                    node_name, entry_func, harness_orchestrator
                )
            entry_func = functools.partial(
                _timed_entry, node_name=node_name, inner=entry_func,
            )
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

        if checkpointer is not None:
            compiled = graph.compile(checkpointer=checkpointer)
        else:
            compiled = graph.compile()
        logger.info(
            "Built workflow '%s': %d nodes, entry=%s%s",
            template_name,
            len(tpl.get("nodes", [])),
            entry,
            " (checkpointed)" if checkpointer else "",
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

    # ── Harness node wrapper ────────────────────────────────────────────

    def _wrap_node_with_harness(
        self,
        node_name: str,
        entry_func: Any,
        orchestrator: object,
    ) -> Any:
        """Wrap a node entry function with governance checks.

        The wrapper:
        1. Captures pre-execution context (state snapshot, node_name)
        2. Runs ``execute_pre()`` — input_safety / permission handlers
        3. If any pre-handler returns REJECT, returns state unchanged
        4. Executes the original node entry function
        5. Captures post-execution context (output, duration)
        6. Runs ``execute_post()`` — structural / fact / hallucination / audit

        Args:
            node_name: Name of the node being wrapped.
            entry_func: The async entry function ``(state) -> state``.
            orchestrator: ``HarnessOrchestrator`` instance.

        Returns:
            Async wrapper function compatible with LangGraph node signature.
        """

        async def _wrapped(state: dict[str, Any]) -> dict[str, Any]:
            # Lazy imports to avoid circular dependency at module level
            from harness.orchestrator.context import (
                PostExecContext,
                PreExecContext,
            )

            base: dict[str, Any] = state.get("base", {})
            user_input: str = base.get("user_input", "")
            user_id: str = base.get("user_id", "")

            # ── Pre-execution check ────────────────────────────────────
            pre_ctx = PreExecContext(
                node_name=node_name,
                raw_input=user_input,
                user_id=user_id,
                state_snapshot=dict(state),
            )
            pre_results = await orchestrator.execute_pre(pre_ctx)  # type: ignore[union-attr]

            has_reject = any(
                r.decision == "reject" for r in pre_results
            )
            if has_reject:
                logger.warning(
                    "Harness pre-check REJECTED for node '%s': %s",
                    node_name,
                    [r.detail for r in pre_results if r.decision == "reject"],
                )
                return state  # Return state unchanged, workflow continues

            # ── Execute node ───────────────────────────────────────────
            t0 = time.perf_counter()
            try:
                result_state = await entry_func(state)
            except Exception as exc:
                # Re-raise LangGraph interrupts — they are control-flow, not errors
                from langgraph.types import Interrupt
                if isinstance(exc, Interrupt):
                    raise
                logger.error(
                    "Node '%s' raised exception during harness wrap: %s",
                    node_name, exc,
                )
                return state
            duration_ms = (time.perf_counter() - t0) * 1000.0

            # ── Post-execution check ───────────────────────────────────
            raw_output = _extract_raw_output(result_state)
            post_ctx = PostExecContext(
                node_name=node_name,
                raw_output=raw_output,
                state_snapshot=dict(result_state),
                duration_ms=duration_ms,
            )
            await orchestrator.execute_post(post_ctx)  # type: ignore[union-attr]

            return result_state

        return _wrapped


def _extract_raw_output(state: dict[str, Any]) -> str:
    """Extract a text summary from the state dict for harness context.

    Tries ``state.writing.content``, ``state.base.raw_output``, or
    serialises the first 2000 chars of the state as fallback.
    """
    writing: dict[str, Any] = state.get("writing", {})
    content = writing.get("content", "")
    if isinstance(content, str) and content.strip():
        return content
    # Fallback: serialise state keys
    return str({k: str(v)[:200] for k, v in state.items()})


# ── Node timing wrapper (module-level) ────────────────────────────

async def _timed_entry(
    state: dict[str, Any],
    *,
    node_name: str,
    inner: Any,
) -> dict[str, Any]:
    """Wrap a node entry with per-node duration logging.

    Logs each node's elapsed time via structlog on completion or failure.
    Compatible with LangGraph node signature ``(state) -> dict``.
    Must be a module-level function so functools.partial works with
    LangGraph's positional ``state`` call convention.
    """
    t0 = time.perf_counter()
    try:
        result = await inner(state)
        duration_ms = (time.perf_counter() - t0) * 1000.0
        print(
            f"[timing] node={node_name} duration_ms={duration_ms:.1f} status=ok",
            flush=True,
        )
        return result
    except Exception:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        print(
            f"[timing] node={node_name} duration_ms={duration_ms:.1f} status=error",
            flush=True,
        )
        raise
