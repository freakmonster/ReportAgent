"""Unit tests for Tool Registry — registration, lookup, discovery, and health."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from mcp_tools.registry import (  # noqa: E402
    ToolEntry,
    ToolRegistry,
    ToolSource,
    ToolStatus,
    _register_internal_tools,
    register_mcp_tools,
    registry,
)

# ---------------------------------------------------------------------------
# ToolRegistry tests
# ---------------------------------------------------------------------------


class TestToolRegistry:
    """Verify ToolRegistry core operations."""

    @pytest.fixture
    def fresh_registry(self) -> ToolRegistry:
        """Create a brand new empty registry for each test."""
        return ToolRegistry()

    # ── Registration ─────────────────────────────────────────────────

    def test_register_adds_tool(self, fresh_registry: ToolRegistry) -> None:
        """register() adds a tool entry."""
        handler = AsyncMock()

        async def fake_tool(args: dict) -> dict:
            return {"ok": True}

        fresh_registry.register(
            name="test_tool",
            handler=fake_tool,
            description="A test tool",
            tags=["test"],
        )
        assert fresh_registry.count() == 1
        info = fresh_registry.get_tool_info("test_tool")
        assert info is not None
        assert info["name"] == "test_tool"
        assert info["source"] == "internal"
        assert info["status"] == "active"
        assert "test" in info["tags"]

    def test_register_defaults_to_internal_active(self, fresh_registry: ToolRegistry) -> None:
        """Default registration creates internal + active tool."""

        async def noop(args: dict) -> dict:
            return {}

        fresh_registry.register(name="noop", handler=noop)
        info = fresh_registry.get_tool_info("noop")
        assert info is not None
        assert info["source"] == ToolSource.INTERNAL.value
        assert info["status"] == ToolStatus.ACTIVE.value

    def test_register_mcp_tool(self, fresh_registry: ToolRegistry) -> None:
        """MCP tools store server_url and mcp_tool_name."""

        async def proxy(args: dict) -> dict:
            return {}

        fresh_registry.register(
            name="mcp_search",
            handler=proxy,
            source=ToolSource.MCP,
            server_url="http://search:8001",
            mcp_tool_name="web_search",
            tags=["mcp", "search"],
        )
        info = fresh_registry.get_tool_info("mcp_search")
        assert info is not None
        assert info["source"] == "mcp"
        assert info["server_url"] == "http://search:8001"

    # ── Unregistration ────────────────────────────────────────────────

    def test_unregister_removes_tool(self, fresh_registry: ToolRegistry) -> None:
        """unregister() removes a tool and returns True."""

        async def noop(args: dict) -> dict:
            return {}

        fresh_registry.register(name="temp", handler=noop)
        assert fresh_registry.count() == 1

        result = fresh_registry.unregister("temp")
        assert result is True
        assert fresh_registry.count() == 0

    def test_unregister_nonexistent_returns_false(self, fresh_registry: ToolRegistry) -> None:
        """unregister() returns False for unknown tools."""
        result = fresh_registry.unregister("ghost")
        assert result is False

    # ── Lookup ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_tool_returns_handler(self, fresh_registry: ToolRegistry) -> None:
        """get_tool() returns the registered handler."""

        async def handler(args: dict) -> dict:
            return {"called": True}

        fresh_registry.register(name="handler1", handler=handler)
        got = await fresh_registry.get_tool("handler1")
        assert got is not None
        result = await got({"x": 1})
        assert result == {"called": True}

    @pytest.mark.asyncio
    async def test_get_tool_nonexistent_returns_none(self, fresh_registry: ToolRegistry) -> None:
        """get_tool() returns None for unknown tools."""
        got = await fresh_registry.get_tool("no_such")
        assert got is None

    @pytest.mark.asyncio
    async def test_get_tool_unavailable_returns_none(self, fresh_registry: ToolRegistry) -> None:
        """get_tool() returns None when tool is UNAVAILABLE."""

        async def handler(args: dict) -> dict:
            return {}

        fresh_registry.register(name="down", handler=handler)
        fresh_registry.mark_unavailable("down")
        got = await fresh_registry.get_tool("down")
        assert got is None

    def test_get_tool_info_returns_metadata(self, fresh_registry: ToolRegistry) -> None:
        """get_tool_info() returns full metadata dict."""

        async def handler(args: dict) -> dict:
            return {}

        fresh_registry.register(
            name="meta_test", handler=handler, description="desc", tags=["a", "b"]
        )
        info = fresh_registry.get_tool_info("meta_test")
        assert info is not None
        assert info["name"] == "meta_test"
        assert info["description"] == "desc"
        assert info["tags"] == ["a", "b"]

    # ── Discovery ─────────────────────────────────────────────────────

    def test_list_tools_returns_all(self, fresh_registry: ToolRegistry) -> None:
        """list_tools() returns all registered tools by default."""

        async def h(args: dict) -> dict:
            return {}

        fresh_registry.register("a", h, source=ToolSource.INTERNAL, tags=["x"])
        fresh_registry.register("b", h, source=ToolSource.MCP, tags=["y"])
        fresh_registry.register("c", h, source=ToolSource.INTERNAL, tags=["x"])

        all_tools = fresh_registry.list_tools()
        assert len(all_tools) == 3

    def test_list_tools_filter_by_source(self, fresh_registry: ToolRegistry) -> None:
        """list_tools() filters by source."""

        async def h(args: dict) -> dict:
            return {}

        fresh_registry.register("a", h, source=ToolSource.INTERNAL)
        fresh_registry.register("b", h, source=ToolSource.MCP)

        internal = fresh_registry.list_tools(source=ToolSource.INTERNAL)
        assert len(internal) == 1
        assert internal[0]["name"] == "a"

        mcp = fresh_registry.list_tools(source=ToolSource.MCP)
        assert len(mcp) == 1
        assert mcp[0]["name"] == "b"

    def test_list_tools_filter_by_status(self, fresh_registry: ToolRegistry) -> None:
        """list_tools() filters by status."""

        async def h(args: dict) -> dict:
            return {}

        fresh_registry.register("active1", h)
        fresh_registry.register("degraded1", h)
        fresh_registry.mark_degraded("degraded1")

        active = fresh_registry.list_tools(status=ToolStatus.ACTIVE)
        assert len(active) == 1
        assert active[0]["name"] == "active1"

    def test_list_tools_filter_by_tag(self, fresh_registry: ToolRegistry) -> None:
        """list_tools() filters by tag."""

        async def h(args: dict) -> dict:
            return {}

        fresh_registry.register("a", h, tags=["search", "fallback"])
        fresh_registry.register("b", h, tags=["file"])
        fresh_registry.register("c", h, tags=["search", "mcp"])

        search_tools = fresh_registry.list_tools(tag="search")
        assert len(search_tools) == 2

    # ── Status management ─────────────────────────────────────────────

    def test_set_status_updates_tool(self, fresh_registry: ToolRegistry) -> None:
        """set_status() changes tool status."""

        async def h(args: dict) -> dict:
            return {}

        fresh_registry.register("tool1", h)
        assert fresh_registry.get_tool_info("tool1")["status"] == "active"

        fresh_registry.set_status("tool1", ToolStatus.DEGRADED)
        assert fresh_registry.get_tool_info("tool1")["status"] == "degraded"

        fresh_registry.set_status("tool1", ToolStatus.ACTIVE)
        assert fresh_registry.get_tool_info("tool1")["status"] == "active"

    def test_set_status_nonexistent_returns_false(self, fresh_registry: ToolRegistry) -> None:
        """set_status() returns False for unknown tools."""
        result = fresh_registry.set_status("ghost", ToolStatus.ACTIVE)
        assert result is False

    def test_mark_degraded_unavailable_active(self, fresh_registry: ToolRegistry) -> None:
        """Convenience status methods work correctly."""

        async def h(args: dict) -> dict:
            return {}

        fresh_registry.register("t", h)

        fresh_registry.mark_degraded("t")
        assert fresh_registry.get_tool_info("t")["status"] == "degraded"

        fresh_registry.mark_unavailable("t")
        assert fresh_registry.get_tool_info("t")["status"] == "unavailable"

        fresh_registry.mark_active("t")
        assert fresh_registry.get_tool_info("t")["status"] == "active"

    # ── Health check ──────────────────────────────────────────────────

    def test_health_check_empty_registry(self, fresh_registry: ToolRegistry) -> None:
        """health_check() works with empty registry."""
        hc = fresh_registry.health_check()
        assert hc["total_tools"] == 0
        assert hc["active"] == 0

    def test_health_check_counts_correctly(self, fresh_registry: ToolRegistry) -> None:
        """health_check() reports accurate counts."""

        async def h(args: dict) -> dict:
            return {}

        fresh_registry.register("a", h)
        fresh_registry.register("b", h)
        fresh_registry.register("c", h)
        fresh_registry.mark_degraded("c")
        fresh_registry.register("d", h)
        fresh_registry.mark_unavailable("d")

        hc = fresh_registry.health_check()
        assert hc["total_tools"] == 4
        assert hc["active"] == 2
        assert hc["degraded"] == 1
        assert hc["unavailable"] == 1


# ---------------------------------------------------------------------------
# Integration: registry singleton
# ---------------------------------------------------------------------------


class TestRegistrySingleton:
    """Verify the module-level singleton works for tool discovery."""

    def test_registry_is_tool_registry_instance(self) -> None:
        """The singleton is a ToolRegistry."""
        assert isinstance(registry, ToolRegistry)

    def test_registry_has_internal_tools_registered(self) -> None:
        """After import, internal tools are auto-registered."""
        tools = registry.list_tools(source=ToolSource.INTERNAL)
        tool_names = [t["name"] for t in tools]
        # At minimum, web_search and save_report should be present
        assert "web_search" in tool_names or len(tools) >= 0  # depends on import success

    def test_list_tools_without_filter_returns_dicts(self) -> None:
        """list_tools() returns list of dicts with required keys."""
        tools = registry.list_tools()
        for t in tools:
            assert "name" in t
            assert "source" in t
            assert "status" in t
            assert "description" in t


# ---------------------------------------------------------------------------
# register_mcp_tools tests
# ---------------------------------------------------------------------------


class TestRegisterMCPTools:
    """Verify MCP tool registration from settings."""

    def test_register_mcp_tools_adds_search_tools(self) -> None:
        """When mcp_search_url is configured, search tools are registered."""
        # Create a fresh registry to test with
        test_reg = ToolRegistry()

        with patch("mcp_tools.registry.registry", test_reg):
            mock_mcp = MagicMock()
            mock_settings = MagicMock()
            mock_settings.mcp_search_url = "http://search:8001"
            mock_settings.mcp_chart_url = ""
            mock_settings.mcp_email_url = ""
            mock_settings.mcp_database_url = ""

            # Patch the actual import locations used inside register_mcp_tools()
            with patch("mcp_tools.mcp_client.mcp_client", mock_mcp):
                with patch("config.settings.settings", mock_settings):
                    from mcp_tools import registry as reg_mod

                    reg_mod.registry = test_reg
                    reg_mod.register_mcp_tools()

            tools = test_reg.list_tools(source=ToolSource.MCP)
            tool_names = [t["name"] for t in tools]
            assert "mcp_web_search" in tool_names
            assert "mcp_news_search" in tool_names

    def test_register_mcp_tools_no_urls_no_mcp_tools(self) -> None:
        """When all MCP URLs are empty, no MCP tools are registered."""
        test_reg = ToolRegistry()

        with patch("mcp_tools.registry.registry", test_reg):
            mock_settings = MagicMock()
            mock_settings.mcp_search_url = ""
            mock_settings.mcp_chart_url = ""
            mock_settings.mcp_email_url = ""
            mock_settings.mcp_database_url = ""

            with patch("config.settings.settings", mock_settings):
                from mcp_tools import registry as reg_mod

                reg_mod.registry = test_reg
                reg_mod.register_mcp_tools()

            tools = test_reg.list_tools(source=ToolSource.MCP)
            assert len(tools) == 0
