"""
Tool Registry — Dynamic tool loading and discovery.

Manages both MCP server tools and internal fallback tools.
Provides:
- Dynamic loading from configuration
- Tool discovery API
- Health status for all registered tools
- Hot-reload support

Design decision (AGENTS.md §6.1): uses a registry dictionary rather than
hardcoded if/elif branches. New tools are added via ``register()`` calls
at module load time, not by modifying control flow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Type alias for an async tool handler
ToolHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, Any]]


class ToolStatus(str, Enum):
    """Status of a registered tool."""

    ACTIVE = "active"  # Tool is registered and available
    DEGRADED = "degraded"  # Tool is registered but marked as fallback
    UNAVAILABLE = "unavailable"  # Tool is registered but currently unavailable


class ToolSource(str, Enum):
    """Source of a tool: internal or MCP server."""

    INTERNAL = "internal"
    MCP = "mcp"


@dataclass
class ToolEntry:
    """Metadata and handler for a registered tool."""

    name: str
    handler: ToolHandler
    source: ToolSource = ToolSource.INTERNAL
    status: ToolStatus = ToolStatus.ACTIVE
    description: str = ""
    server_url: str = ""  # Only for MCP tools
    mcp_tool_name: str = ""  # The tool name on the MCP server
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Dynamic tool registry with discovery and health check support.

    Architecture (AGENTS.md §6.1 compliant):
    - Tools are registered via ``register()``, not selected via if/elif.
    - MCP server tools are configured externally (YAML/env), not hardcoded.
    - Discovery API returns all registered tools with status.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}
        self._initialized: bool = False

    # ── Registration ──────────────────────────────────────────────────

    def register(
        self,
        name: str,
        handler: ToolHandler,
        source: ToolSource = ToolSource.INTERNAL,
        description: str = "",
        server_url: str = "",
        mcp_tool_name: str = "",
        tags: list[str] | None = None,
    ) -> None:
        """Register a tool in the registry.

        Args:
            name: Unique tool name (used for lookup).
            handler: Async callable that receives arguments dict.
            source: Whether this is an INTERNAL or MCP tool.
            description: Human-readable description.
            server_url: MCP server URL (only for MCP tools).
            mcp_tool_name: The tool's endpoint name on the MCP server.
            tags: Optional tags for categorization.
        """
        entry = ToolEntry(
            name=name,
            handler=handler,
            source=source,
            status=ToolStatus.ACTIVE,
            description=description,
            server_url=server_url,
            mcp_tool_name=mcp_tool_name or name,
            tags=tags or [],
        )
        self._tools[name] = entry
        logger.debug("Registered tool: %s (source=%s)", name, source.value)

    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry.

        Returns:
            True if the tool was found and removed.
        """
        if name in self._tools:
            del self._tools[name]
            logger.debug("Unregistered tool: %s", name)
            return True
        return False

    # ── Lookup ─────────────────────────────────────────────────────────

    async def get_tool(self, name: str) -> ToolHandler | None:
        """Get a tool's handler by name.

        Returns:
            The async handler callable, or None if not found.
        """
        entry = self._tools.get(name)
        if entry is None:
            logger.warning("Tool not found: %s", name)
            return None

        if entry.status == ToolStatus.UNAVAILABLE:
            logger.warning("Tool '%s' is unavailable", name)
            return None

        return entry.handler

    def get_tool_info(self, name: str) -> dict[str, Any] | None:
        """Get metadata for a registered tool.

        Returns:
            Dict with tool metadata, or None if not found.
        """
        entry = self._tools.get(name)
        if entry is None:
            return None
        return {
            "name": entry.name,
            "source": entry.source.value,
            "status": entry.status.value,
            "description": entry.description,
            "server_url": entry.server_url,
            "tags": entry.tags,
        }

    # ── Discovery ───────────────────────────────────────────────────────

    def list_tools(
        self,
        source: ToolSource | None = None,
        status: ToolStatus | None = None,
        tag: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all registered tools, optionally filtered.

        Args:
            source: Filter by tool source (INTERNAL or MCP).
            status: Filter by tool status.
            tag: Filter by tag.

        Returns:
            List of tool info dicts.
        """
        result: list[dict[str, Any]] = []
        for entry in self._tools.values():
            if source is not None and entry.source != source:
                continue
            if status is not None and entry.status != status:
                continue
            if tag is not None and tag not in entry.tags:
                continue
            result.append(
                {
                    "name": entry.name,
                    "source": entry.source.value,
                    "status": entry.status.value,
                    "description": entry.description,
                    "server_url": entry.server_url,
                    "tags": entry.tags,
                }
            )
        return result

    def count(self) -> int:
        """Return the total number of registered tools."""
        return len(self._tools)

    # ── Status management ───────────────────────────────────────────────

    def set_status(self, name: str, status: ToolStatus) -> bool:
        """Update the status of a registered tool.

        Args:
            name: Tool name.
            status: New status.

        Returns:
            True if the tool was found and updated.
        """
        entry = self._tools.get(name)
        if entry is None:
            return False
        entry.status = status
        logger.info("Tool '%s' status changed to %s", name, status.value)
        return True

    def mark_degraded(self, name: str) -> None:
        """Mark a tool as DEGRADED (fallback mode)."""
        self.set_status(name, ToolStatus.DEGRADED)

    def mark_unavailable(self, name: str) -> None:
        """Mark a tool as UNAVAILABLE."""
        self.set_status(name, ToolStatus.UNAVAILABLE)

    def mark_active(self, name: str) -> None:
        """Restore a tool to ACTIVE status."""
        self.set_status(name, ToolStatus.ACTIVE)

    # ── Health ─────────────────────────────────────────────────────────

    def health_check(self) -> dict[str, Any]:
        """Return health summary for all registered tools."""
        total = len(self._tools)
        active = sum(1 for e in self._tools.values() if e.status == ToolStatus.ACTIVE)
        degraded = sum(1 for e in self._tools.values() if e.status == ToolStatus.DEGRADED)
        unavailable = sum(1 for e in self._tools.values() if e.status == ToolStatus.UNAVAILABLE)

        return {
            "total_tools": total,
            "active": active,
            "degraded": degraded,
            "unavailable": unavailable,
            "details": {
                name: {
                    "source": entry.source.value,
                    "status": entry.status.value,
                }
                for name, entry in self._tools.items()
            },
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

registry = ToolRegistry()


# ---------------------------------------------------------------------------
# Auto-registration of internal tools (called once at first import)
# ---------------------------------------------------------------------------


def _register_internal_tools() -> None:
    """Register all built-in internal tools.

    This is called once when the module is first imported.
    Internal tools are always available (no external dependencies).
    """
    if registry._initialized:
        return
    registry._initialized = True

    try:
        from mcp_tools.internal_tools.web_search import (
            news_search_tool,
            web_search_tool,
        )

        registry.register(
            name="web_search",
            handler=web_search_tool,
            source=ToolSource.INTERNAL,
            description="Internal web search (fallback when MCP search unavailable)",
            tags=["search", "fallback"],
        )
        registry.register(
            name="news_search",
            handler=news_search_tool,
            source=ToolSource.INTERNAL,
            description="Internal news search (fallback)",
            tags=["search", "news", "fallback"],
        )
    except ImportError as exc:
        logger.warning("Internal search tools not registered: %s", exc)

    try:
        from mcp_tools.internal_tools.file_manager import (
            read_report_tool,
            save_report_tool,
        )

        registry.register(
            name="save_report",
            handler=save_report_tool,
            source=ToolSource.INTERNAL,
            description="Save a research report to disk",
            tags=["file", "report"],
        )
        registry.register(
            name="read_report",
            handler=read_report_tool,
            source=ToolSource.INTERNAL,
            description="Read a saved research report from disk",
            tags=["file", "report"],
        )
    except ImportError as exc:
        logger.warning("File manager tools not registered: %s", exc)


# ── Register MCP server tools ──────────────────────────────────────────


def register_mcp_tools() -> None:
    """Register MCP server tools from configuration.

    Reads MCP server URLs from settings and registers corresponding
    proxy handlers that call through the MCP client.
    """
    try:
        from config.settings import settings
        from mcp_tools.mcp_client import mcp_client
    except ImportError:
        logger.warning("MCP client or settings not available, skipping MCP tool registration")
        return

    # ── Search server tools ─────────────────────────────────────────
    if settings.mcp_search_url:
        registry.register(
            name="mcp_web_search",
            handler=_make_mcp_proxy(
                mcp_client, settings.mcp_search_url, "web_search", "mcp-search"
            ),
            source=ToolSource.MCP,
            description="MCP web search via Tavily API",
            server_url=settings.mcp_search_url,
            mcp_tool_name="web_search",
            tags=["search", "mcp", "external"],
        )
        registry.register(
            name="mcp_news_search",
            handler=_make_mcp_proxy(
                mcp_client, settings.mcp_search_url, "news_search", "mcp-search"
            ),
            source=ToolSource.MCP,
            description="MCP news search via Tavily API",
            server_url=settings.mcp_search_url,
            mcp_tool_name="news_search",
            tags=["search", "news", "mcp", "external"],
        )
        # Register degradation mapping
        mcp_client.register_degradation(settings.mcp_search_url, "web_search")

    # ── Chart server tools ─────────────────────────────────────────
    if settings.mcp_chart_url:
        for chart_type in ("generate_line_chart", "generate_bar_chart", "generate_pie_chart"):
            registry.register(
                name=f"mcp_{chart_type}",
                handler=_make_mcp_proxy(
                    mcp_client, settings.mcp_chart_url, chart_type, "mcp-chart"
                ),
                source=ToolSource.MCP,
                description=f"MCP {chart_type.replace('_', ' ')}",
                server_url=settings.mcp_chart_url,
                mcp_tool_name=chart_type,
                tags=["chart", "mcp", "external"],
            )

    # ── Email server tools ─────────────────────────────────────────
    if settings.mcp_email_url:
        registry.register(
            name="mcp_send_email",
            handler=_make_mcp_proxy(mcp_client, settings.mcp_email_url, "send_email", "mcp-email"),
            source=ToolSource.MCP,
            description="MCP email sending",
            server_url=settings.mcp_email_url,
            mcp_tool_name="send_email",
            tags=["email", "mcp", "external"],
        )

    # ── Database tools (via community Docker image) ─────────────────
    if settings.mcp_database_url:
        registry.register(
            name="mcp_db_query",
            handler=_make_mcp_proxy(mcp_client, settings.mcp_database_url, "query", "mcp-database"),
            source=ToolSource.MCP,
            description="MCP database query (postgresql-mcp community image)",
            server_url=settings.mcp_database_url,
            mcp_tool_name="query",
            tags=["database", "mcp", "external"],
        )


def _make_mcp_proxy(
    client: object,
    server_url: str,
    tool_name: str,
    server_name: str,
) -> ToolHandler:
    """Create an async proxy handler that calls an MCP tool via the MCP client.

    Args:
        client: MCPClient instance.
        server_url: MCP server base URL.
        tool_name: Tool name on the MCP server.
        server_name: Human-readable server name.

    Returns:
        Async callable suitable for registry registration.
    """

    async def proxy(arguments: dict[str, Any]) -> dict[str, Any]:
        result = await client.call(  # type: ignore[union-attr]
            server_url=server_url,
            tool_name=tool_name,
            arguments=arguments,
            server_name=server_name,
        )
        if result.success:
            return result.data or {}
        return {"error": result.error, "degraded": True}

    return proxy


# ── Register MCP std tools (Bailian / AntV / external standard MCP) ──

# All chart types: core 3 (backward-compatible) + AntV-unique
_CHART_TYPES_CORE: list[tuple[str, str]] = [
    ("generate_bar_chart", "bar"),
    ("generate_line_chart", "line"),
    ("generate_pie_chart", "pie"),
]

_CHART_TYPES_ANTV: list[tuple[str, str]] = [
    ("generate_area_chart", "area"),
    ("generate_boxplot_chart", "boxplot"),
    ("generate_column_chart", "column"),
    ("generate_district_map", "district_map"),
    ("generate_dual_axes_chart", "dual_axes"),
    ("generate_fishbone_diagram", "fishbone"),
    ("generate_flow_diagram", "flow"),
    ("generate_funnel_chart", "funnel"),
    ("generate_histogram_chart", "histogram"),
    ("generate_liquid_chart", "liquid"),
    ("generate_mind_map", "mind_map"),
    ("generate_network_graph", "network"),
    ("generate_organization_chart", "organization"),
    ("generate_path_map", "path_map"),
    ("generate_pin_map", "pin_map"),
    ("generate_radar_chart", "radar"),
    ("generate_sankey_chart", "sankey"),
    ("generate_scatter_chart", "scatter"),
    ("generate_treemap_chart", "treemap"),
    ("generate_venn_chart", "venn"),
    ("generate_violin_chart", "violin"),
    ("generate_word_cloud_chart", "word_cloud"),
]

_ALL_CHART_TYPES: list[tuple[str, str]] = _CHART_TYPES_CORE + _CHART_TYPES_ANTV


def _make_mcp_std_proxy(
    client: object,
    server_url: str,
    tool_name: str,
    server_name: str,
) -> ToolHandler:
    """Create an async proxy handler that calls a standard MCP tool via MCPStdClient.

    Args:
        client: MCPStdClient instance.
        server_url: Standard MCP server base URL.
        tool_name: Tool name on the MCP std server.
        server_name: Human-readable server name.

    Returns:
        Async callable suitable for registry registration.
    """

    async def proxy(arguments: dict[str, Any]) -> dict[str, Any]:
        result = await client.call(  # type: ignore[union-attr]
            server_url=server_url,
            tool_name=tool_name,
            arguments=arguments,
            server_name=server_name,
        )
        if result.success:
            return result.data or {}
        return {"error": result.error, "degraded": True}

    return proxy


def register_mcp_std_tools() -> None:
    """Register standard MCP chart tools (Bailian / AntV).

    Swaps ACTIVE/DEGRADED status based on the ``chart_backend`` configuration.

    Supported backends:
    - ``"matplotlib"`` (default): matplotlib ACTIVE, bailian + antv DEGRADED
    - ``"bailian"``: bailian ACTIVE (core 3 tools), matplotlib + antv DEGRADED
    - ``"antv"``: antv ACTIVE (core 3 + all antv-unique tools), matplotlib + bailian DEGRADED
    """
    try:
        from config.settings import settings
        from mcp_tools.mcp_std_client import mcp_std_client
    except ImportError:
        logger.warning("MCPStdClient or settings not available, skipping std MCP registration")
        return

    chart_backend = settings.chart_backend
    mcp_std_chart_url = settings.mcp_std_chart_url
    mcp_antv_url = settings.mcp_antv_url

    # ── Helper: get matplotlib handler (REST MCPClient) ─────────────────
    def _get_matplotlib_handler(tool_name: str) -> ToolHandler:
        if settings.mcp_chart_url:
            try:
                from mcp_tools.mcp_client import mcp_client

                return _make_mcp_proxy(mcp_client, settings.mcp_chart_url, tool_name, "mcp-chart")
            except ImportError:
                pass
        return _noop_handler

    # ── Helper: get bailian handler ─────────────────────────────────────
    def _get_bailian_handler(tool_name: str) -> ToolHandler | None:
        if not mcp_std_chart_url:
            return None
        return _make_mcp_std_proxy(mcp_std_client, mcp_std_chart_url, tool_name, "bailian-chart")

    # ── Helper: get antv handler ────────────────────────────────────────
    def _get_antv_handler(tool_name: str) -> ToolHandler | None:
        if not mcp_antv_url:
            return None
        return _make_mcp_std_proxy(mcp_std_client, mcp_antv_url, tool_name, "antv-chart")

    # ── Backend: matplotlib (default) ───────────────────────────────────
    if chart_backend == "matplotlib":
        # matplotlib is already ACTIVE from register_mcp_tools()
        # Register bailian core tools as DEGRADED
        if mcp_std_chart_url:
            for tool_name, short in _CHART_TYPES_CORE:
                registry.register(
                    name=f"mcp_chart_{short}_bailian",
                    handler=_get_bailian_handler(tool_name),  # type: ignore[arg-type]
                    source=ToolSource.MCP,
                    description=f"Bailian MCP {short} chart (fallback)",
                    server_url=mcp_std_chart_url,
                    mcp_tool_name=tool_name,
                    tags=["chart", "mcp_std", "bailian", "fallback"],
                )
                registry.mark_degraded(f"mcp_chart_{short}_bailian")

        # Register antv tools as DEGRADED
        if mcp_antv_url:
            for tool_name, short in _ALL_CHART_TYPES:
                handler = _get_antv_handler(tool_name)
                if handler is None:
                    continue
                if short in ("bar", "line", "pie"):
                    name = f"mcp_chart_{short}_antv"
                else:
                    name = f"mcp_generate_{tool_name}"
                registry.register(
                    name=name,
                    handler=handler,
                    source=ToolSource.MCP,
                    description=f"AntV MCP {short} chart (fallback)",
                    server_url=mcp_antv_url,
                    mcp_tool_name=tool_name,
                    tags=["chart", "mcp_std", "antv", "fallback"],
                )
                registry.mark_degraded(name)

    # ── Backend: bailian ────────────────────────────────────────────────
    elif chart_backend == "bailian":
        if mcp_std_chart_url:
            # Bailian core tools ACTIVE
            for tool_name, short in _CHART_TYPES_CORE:
                registry.register(
                    name=f"mcp_{tool_name}",
                    handler=_get_bailian_handler(tool_name),  # type: ignore[arg-type]
                    source=ToolSource.MCP,
                    description=f"Bailian MCP {short} chart",
                    server_url=mcp_std_chart_url,
                    mcp_tool_name=tool_name,
                    tags=["chart", "mcp_std", "bailian"],
                )

            # matplotlib core tools DEGRADED
            for tool_name, short in _CHART_TYPES_CORE:
                registry.register(
                    name=f"mcp_chart_{short}_matplotlib",
                    handler=_get_matplotlib_handler(tool_name),
                    source=ToolSource.MCP,
                    description=f"Matplotlib {short} chart (fallback)",
                    server_url=settings.mcp_chart_url,
                    mcp_tool_name=tool_name,
                    tags=["chart", "mcp", "matplotlib", "fallback"],
                )
                registry.mark_degraded(f"mcp_chart_{short}_matplotlib")

            # antv tools DEGRADED
            if mcp_antv_url:
                for tool_name, short in _ALL_CHART_TYPES:
                    handler = _get_antv_handler(tool_name)
                    if handler is None:
                        continue
                    if short in ("bar", "line", "pie"):
                        name = f"mcp_chart_{short}_antv"
                    else:
                        name = f"mcp_generate_{tool_name}"
                    registry.register(
                        name=name,
                        handler=handler,
                        source=ToolSource.MCP,
                        description=f"AntV MCP {short} chart (fallback)",
                        server_url=mcp_antv_url,
                        mcp_tool_name=tool_name,
                        tags=["chart", "mcp_std", "antv", "fallback"],
                    )
                    registry.mark_degraded(name)

            logger.info(
                "MCP std tools: bailian ACTIVE (core 3, %s), matplotlib + antv DEGRADED",
                mcp_std_chart_url,
            )

    # ── Backend: antv ───────────────────────────────────────────────────
    elif chart_backend == "antv":
        if mcp_antv_url:
            # Antv core tools ACTIVE (overwrite matplotlib)
            for tool_name, short in _CHART_TYPES_CORE:
                registry.register(
                    name=f"mcp_{tool_name}",
                    handler=_get_antv_handler(tool_name),  # type: ignore[arg-type]
                    source=ToolSource.MCP,
                    description=f"AntV MCP {short} chart",
                    server_url=mcp_antv_url,
                    mcp_tool_name=tool_name,
                    tags=["chart", "mcp_std", "antv"],
                )

            # AntV-unique tools ACTIVE
            for tool_name, short in _CHART_TYPES_ANTV:
                handler = _get_antv_handler(tool_name)
                if handler is None:
                    continue
                registry.register(
                    name=f"mcp_{tool_name}",
                    handler=handler,
                    source=ToolSource.MCP,
                    description=f"AntV MCP {short} chart",
                    server_url=mcp_antv_url,
                    mcp_tool_name=tool_name,
                    tags=["chart", "mcp_std", "antv"],
                )

            # matplotlib core tools DEGRADED
            for tool_name, short in _CHART_TYPES_CORE:
                registry.register(
                    name=f"mcp_chart_{short}_matplotlib",
                    handler=_get_matplotlib_handler(tool_name),
                    source=ToolSource.MCP,
                    description=f"Matplotlib {short} chart (fallback)",
                    server_url=settings.mcp_chart_url,
                    mcp_tool_name=tool_name,
                    tags=["chart", "mcp", "matplotlib", "fallback"],
                )
                registry.mark_degraded(f"mcp_chart_{short}_matplotlib")

            # bailian core tools DEGRADED
            if mcp_std_chart_url:
                for tool_name, short in _CHART_TYPES_CORE:
                    handler = _get_bailian_handler(tool_name)
                    if handler is None:
                        continue
                    registry.register(
                        name=f"mcp_chart_{short}_bailian",
                        handler=handler,
                        source=ToolSource.MCP,
                        description=f"Bailian MCP {short} chart (fallback)",
                        server_url=mcp_std_chart_url,
                        mcp_tool_name=tool_name,
                        tags=["chart", "mcp_std", "bailian", "fallback"],
                    )
                    registry.mark_degraded(f"mcp_chart_{short}_bailian")

            logger.info(
                "MCP std tools: antv ACTIVE (%d tools, %s), matplotlib + bailian DEGRADED",
                len(_ALL_CHART_TYPES),
                mcp_antv_url,
            )


async def _noop_handler(_arguments: dict[str, Any]) -> dict[str, Any]:
    """No-op handler for unavailable tools."""
    return {"error": "Tool unavailable", "degraded": True}


# ── Initialize on import ───────────────────────────────────────────────

_register_internal_tools()
register_mcp_tools()
register_mcp_std_tools()
