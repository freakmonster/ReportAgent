"""Unit tests for MCP Std Client — Streamable HTTP MCP client."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from mcp_tools.mcp_client import MCPToolResult  # noqa: E402
from mcp_tools.mcp_std_client import MCPStdClient  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def std_client() -> MCPStdClient:
    """Create a fresh MCPStdClient for each test."""
    return MCPStdClient()


@pytest.fixture
def mock_call_tool_result() -> MagicMock:
    """Mock CallToolResult with text content."""
    result = MagicMock()
    content_item = MagicMock()
    content_item.text = '{"chart_type": "bar", "image_base64": "base64data"}'
    result.content = [content_item]
    return result


# ---------------------------------------------------------------------------
# Tests: call() success path
# ---------------------------------------------------------------------------


class TestMCPStdClientCallSuccess:
    """Verify MCPStdClient.call() returns success on valid MCP response."""

    @patch("mcp_tools.mcp_std_client.MCPStdClient._ensure_api_key")
    @patch("mcp.client.streamable_http.streamablehttp_client")
    @patch("mcp.ClientSession")
    async def test_call_success_with_text_response(
        self,
        mock_session_cls: MagicMock,
        mock_streamable: MagicMock,
        mock_api_key: MagicMock,
        std_client: MCPStdClient,
        mock_call_tool_result: MagicMock,
    ) -> None:
        """Successful call with JSON text response returns MCPToolResult(success=True)."""
        mock_api_key.return_value = "fake-api-key"

        # Setup mock session
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_call_tool_result)
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        # Setup mock streamable
        mock_streamable.return_value.__aenter__.return_value = (
            MagicMock(),  # read
            MagicMock(),  # write
            MagicMock(),  # get_session_id
        )

        result = await std_client.call(
            server_url="https://dashscope.aliyuncs.com/api/mcp",
            tool_name="generate_bar_chart",
            arguments={"title": "Test"},
            server_name="bailian",
        )

        assert result.success is True
        assert result.server_name == "bailian"
        assert result.tool_name == "generate_bar_chart"
        assert result.data is not None
        assert "chart_type" in result.data

    @patch("mcp_tools.mcp_std_client.MCPStdClient._ensure_api_key")
    @patch("mcp.client.streamable_http.streamablehttp_client")
    @patch("mcp.ClientSession")
    async def test_call_success_with_plain_text(
        self,
        mock_session_cls: MagicMock,
        mock_streamable: MagicMock,
        mock_api_key: MagicMock,
        std_client: MCPStdClient,
    ) -> None:
        """Plain text (non-JSON) response is wrapped in {'text': ...}."""
        mock_api_key.return_value = "fake-api-key"

        result_item = MagicMock()
        result_item.text = "plain text output"
        result_item2 = MagicMock()
        result_item2.text = None  # no text attribute value
        call_result = MagicMock()
        call_result.content = [result_item]

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=call_result)
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        mock_streamable.return_value.__aenter__.return_value = (
            MagicMock(), MagicMock(), MagicMock()
        )

        result = await std_client.call(
            server_url="https://dashscope.aliyuncs.com/api/mcp",
            tool_name="generate_bar_chart",
            arguments={"title": "Test"},
        )

        assert result.success is True
        assert result.data == {"text": "plain text output"}


# ---------------------------------------------------------------------------
# Tests: call() failure path
# ---------------------------------------------------------------------------


class TestMCPStdClientCallFailure:
    """Verify MCPStdClient.call() returns failure gracefully."""

    async def test_call_no_api_key(self, std_client: MCPStdClient) -> None:
        """Missing API key returns success=False."""
        std_client._api_key = ""

        result = await std_client.call(
            server_url="https://dashscope.aliyuncs.com/api/mcp",
            tool_name="generate_bar_chart",
            arguments={"title": "Test"},
        )

        assert result.success is False
        assert "not configured" in result.error

    @patch("mcp_tools.mcp_std_client.MCPStdClient._ensure_api_key")
    @patch("mcp.client.streamable_http.streamablehttp_client")
    async def test_call_connection_error(
        self,
        mock_streamable: MagicMock,
        mock_api_key: MagicMock,
        std_client: MCPStdClient,
    ) -> None:
        """Connection failure returns success=False with error message."""
        mock_api_key.return_value = "fake-api-key"
        mock_streamable.side_effect = ConnectionError("Connection refused")

        result = await std_client.call(
            server_url="https://dashscope.aliyuncs.com/api/mcp",
            tool_name="generate_bar_chart",
            arguments={"title": "Test"},
            server_name="bailian",
        )

        assert result.success is False
        assert "Connection refused" in result.error
        assert result.server_name == "bailian"
        assert result.tool_name == "generate_bar_chart"

    @patch("mcp_tools.mcp_std_client.MCPStdClient._ensure_api_key")
    @patch("mcp.client.streamable_http.streamablehttp_client")
    @patch("mcp.ClientSession")
    async def test_call_tool_error(
        self,
        mock_session_cls: MagicMock,
        mock_streamable: MagicMock,
        mock_api_key: MagicMock,
        std_client: MCPStdClient,
    ) -> None:
        """MCP session.call_tool() raises → success=False, no crash."""
        mock_api_key.return_value = "fake-api-key"

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(side_effect=RuntimeError("Tool not found"))
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        mock_streamable.return_value.__aenter__.return_value = (
            MagicMock(), MagicMock(), MagicMock()
        )

        result = await std_client.call(
            server_url="https://dashscope.aliyuncs.com/api/mcp",
            tool_name="unknown_tool",
            arguments={},
        )

        assert result.success is False
        assert "Tool not found" in result.error


# ---------------------------------------------------------------------------
# Tests: call() signature compatibility
# ---------------------------------------------------------------------------


class TestMCPStdClientSignatureCompatibility:
    """MCPStdClient.call() must match MCPClient.call() signature."""

    async def test_signature_matches_mcpclient(self) -> None:
        """call() accepts (server_url, tool_name, arguments, server_name)."""
        import inspect

        from mcp_tools.mcp_client import MCPClient

        std_sig = inspect.signature(MCPStdClient.call)
        mcp_sig = inspect.signature(MCPClient.call)

        std_params = set(std_sig.parameters.keys())
        mcp_params = set(mcp_sig.parameters.keys())

        assert std_params == mcp_params, f"Signature mismatch: {std_params} != {mcp_params}"
