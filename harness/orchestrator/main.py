"""
Harness Orchestrator — dynamic handler chain executor (V2.2 Chain of Responsibility).

Loads handlers from config/handler_chain.yaml, executes them sequentially,
short-circuits on REJECT, and supports SIGHUP-based hot reload.

AGENTS.md §1.1 constraint:
    严禁 if isinstance(handler, InputSafetyHandler) 等硬编码判断。
    The orchestrator treats all handlers generically via the HarnessHandler ABC.
"""

from __future__ import annotations

import importlib
import logging
import signal
from pathlib import Path
from typing import Any

import yaml

from harness.handlers.base import HandlerDecision, HandlerResult, HarnessHandler
from harness.orchestrator.context import PostExecContext, PreExecContext

logger = logging.getLogger(__name__)

# Mapping from YAML handler names to module paths
_HANDLER_MODULE_MAP: dict[str, str] = {
    "input_safety_handler": "harness.handlers.input_safety_handler",
    "permission_handler": "harness.handlers.permission_handler",
    "structural_handler": "harness.handlers.structural_handler",
    "fact_stage1_handler": "harness.handlers.fact_stage1_handler",
    "fact_stage2_handler": "harness.handlers.fact_stage2_handler",
    "hallucination_handler": "harness.handlers.hallucination_handler",
    "audit_handler": "harness.handlers.audit_handler",
}


class HarnessOrchestrator:
    """Dynamic handler chain executor.

    Loads handler classes from YAML config, instantiates them, and
    executes the chain against pre/post execution contexts.

    Design:
    - All handlers implement ``HarnessHandler`` (ABC).
    - The orchestrator does NOT know concrete handler types.
    - Chain order is fully configurable via config/handler_chain.yaml.
    - AuditHandler is always last (enforced by loading order).
    - SIGHUP triggers chain reload without process restart.
    """

    def __init__(self, config_path: str | None = None) -> None:
        self._config_path = config_path or str(
            Path(__file__).resolve().parent.parent.parent / "config" / "handler_chain.yaml"
        )
        self._handlers: list[HarnessHandler] = []
        self._reload_requested: bool = False
        self._load_chain()

        # Register SIGHUP for hot reload (Unix) or CTRL_BREAK (Windows)
        try:
            signal.signal(signal.SIGHUP, self._handle_sighup)
        except AttributeError:
            pass  # Windows does not have SIGHUP

    # ── Chain loading ──────────────────────────────────────────────────

    def _load_chain(self, workflow_type: str = "") -> None:
        """(Re)load the handler chain from YAML config.

        If *workflow_type* is given and the config has a matching
        override, that chain is used instead of the default.

        Args:
            workflow_type: Optional workflow type (e.g. 'flash_news').
        """
        try:
            path = Path(self._config_path)
            if not path.exists():
                logger.warning("Handler chain config not found at %s", path)
                return

            config: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError) as exc:
            logger.error("Failed to load handler chain config: %s", exc)
            return

        # Select chain: workflow override or default
        if workflow_type and "workflow_overrides" in config:
            override = config["workflow_overrides"].get(workflow_type, {})
            chain_names = override.get("handler_chain", [])
        else:
            chain_names = config.get("handler_chain", [])

        if not chain_names:
            logger.warning("Empty handler chain for workflow '%s'", workflow_type)
            return

        # Instantiate handlers
        new_handlers: list[HarnessHandler] = []
        for name in chain_names:
            module_path = _HANDLER_MODULE_MAP.get(name)
            if module_path is None:
                logger.warning("Unknown handler '%s', skipping", name)
                continue

            try:
                module = importlib.import_module(module_path)
                # Convention: handler class name is PascalCase of the module name
                class_name = "".join(part.capitalize() for part in name.split("_"))
                handler_cls = getattr(module, class_name)
                instance = handler_cls()
                new_handlers.append(instance)
                logger.debug("Loaded handler: %s", class_name)
            except (ImportError, AttributeError) as exc:
                logger.error("Failed to load handler '%s': %s", name, exc)

        self._handlers = new_handlers
        logger.info(
            "Loaded %d handlers for workflow '%s': %s",
            len(self._handlers),
            workflow_type or "default",
            [h.name for h in self._handlers],
        )

    def reload(self, workflow_type: str = "") -> None:
        """Public API to reload the handler chain (e.g., after YAML change)."""
        self._load_chain(workflow_type)

    # ── Chain execution (dual-phase) ───────────────────────────────────

    async def execute_pre(
        self,
        pre_ctx: PreExecContext,
        workflow_type: str = "",
    ) -> list[HandlerResult]:
        """Run pre-execution handler chain (input_safety, permission).

        Each handler receives ``(pre_ctx, None)``.  Post-only handlers
        (structural, fact_stage, etc.) automatically return PASS since
        they have no post-context to check.

        Args:
            pre_ctx: Context captured before node execution.
            workflow_type: Optional workflow type for chain selection.

        Returns:
            List of HandlerResult.  If any decision is REJECT the node
            should NOT execute.
        """
        return await self._execute_chain(pre_ctx, None, workflow_type)

    async def execute_post(
        self,
        post_ctx: PostExecContext,
        workflow_type: str = "",
    ) -> list[HandlerResult]:
        """Run post-execution handler chain (structural, fact, audit).

        Each handler receives ``(None, post_ctx)``.  Pre-only handlers
        automatically return PASS.

        Args:
            post_ctx: Context captured after node execution.
            workflow_type: Optional workflow type for chain selection.

        Returns:
            List of HandlerResult.  Audit handler always returns PASS.
        """
        return await self._execute_chain(None, post_ctx, workflow_type)

    async def _execute_chain(
        self,
        pre_ctx: PreExecContext | None,
        post_ctx: PostExecContext | None,
        workflow_type: str = "",
    ) -> list[HandlerResult]:
        """Internal: run the loaded handler chain.

        Each handler's ``handle()`` is called in order.  If any returns
        ``REJECT`` the chain short-circuits immediately.  If any returns
        ``FAIL`` the chain continues but the failure is recorded.

        Args:
            pre_ctx: Pre-execution context (or None for post-only runs).
            post_ctx: Post-execution context (or None for pre-only runs).
            workflow_type: Optional workflow type for chain selection.

        Returns:
            List of HandlerResult for every handler that executed.
        """
        if workflow_type and not self._handlers:
            self._load_chain(workflow_type)

        if self._reload_requested:
            self._load_chain(workflow_type)
            self._reload_requested = False

        results: list[HandlerResult] = []

        for handler in self._handlers:
            try:
                result = await handler.handle(pre_ctx, post_ctx)
                result.handler_name = handler.name
                results.append(result)

                if result.decision == HandlerDecision.REJECT:
                    logger.warning("Handler '%s' REJECTED: %s", handler.name, result.detail)
                    break
                if result.decision == HandlerDecision.FAIL:
                    logger.info("Handler '%s' FAILED: %s", handler.name, result.detail)
            except Exception as exc:
                logger.error("Handler '%s' raised exception: %s", handler.name, exc)
                results.append(
                    HandlerResult(
                        decision=HandlerDecision.FAIL,
                        detail=f"Handler error: {exc}",
                        handler_name=handler.name,
                    )
                )

        return results

    # ── SIGHUP handler ────────────────────────────────────────────────

    def _handle_sighup(self, signum: int, frame: object) -> None:
        """Signal handler for SIGHUP — marks chain for reload."""
        logger.info("Received SIGHUP, will reload handler chain on next execute()")
        self._reload_requested = True

    # ── Introspection ──────────────────────────────────────────────────

    @property
    def handler_names(self) -> list[str]:
        """Return names of currently loaded handlers."""
        return [h.name for h in self._handlers]

    @property
    def handler_count(self) -> int:
        """Return number of loaded handlers."""
        return len(self._handlers)
