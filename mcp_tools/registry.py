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


# ── Initialize on import ───────────────────────────────────────────────

_register_internal_tools()
register_mcp_tools()
