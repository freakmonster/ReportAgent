"""
MCP Std Client — 标准 MCP 协议（Streamable HTTP）客户端。

使用 mcp SDK 连接阿里云百炼等外部标准 MCP 服务。
复用 mcp_client.py 的 MCPToolResult / CircuitState 数据类型，
call() 签名与 MCPClient 保持一致。
"""

from __future__ import annotations

import logging
from typing import Any

from mcp_tools.mcp_client import MCPToolResult

logger = logging.getLogger(__name__)


class MCPStdClient:
    """标准 MCP 协议客户端，基于 mcp SDK 的 streamablehttp_client。

    与 MCPClient (HTTP REST) 共享相同的 call() 接口签名，
    支持注册到 ToolRegistry 时使用一致的回调模式。
    """

    def __init__(self) -> None:
        self._api_key: str | None = None

    # ── lazy init ───────────────────────────────────────────────────────

    def _ensure_api_key(self) -> str:
        """Lazily read QWEN_API_KEY (DASHSCOPE_API_KEY) from settings."""
        if self._api_key is None:
            from config.settings import settings

            self._api_key = settings.qwen_api_key
        return self._api_key

    # ── core call method ────────────────────────────────────────────────

    async def call(
        self,
        server_url: str,
        tool_name: str,
        arguments: dict[str, Any],
        server_name: str = "",
    ) -> MCPToolResult:
        """Call a tool on a standard MCP (Streamable HTTP) server.

        Args:
            server_url: Base URL of the MCP std server (e.g. https://dashscope.aliyuncs.com/...).
            tool_name: Name of the tool to call.
            arguments: Tool-specific arguments.
            server_name: Human-readable server name for logging.

        Returns:
            MCPToolResult with success flag, data, and optional error info.
        """
        api_key = self._ensure_api_key()
        if not api_key:
            return MCPToolResult(
                success=False,
                error="QWEN_API_KEY (DASHSCOPE_API_KEY) not configured",
                server_name=server_name or server_url,
                tool_name=tool_name,
            )

        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            headers = {"Authorization": f"Bearer {api_key}"}

            async with streamablehttp_client(server_url, headers=headers) as (
                read,
                write,
                get_session_id,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=arguments)

            result_dict: dict[str, Any] = {}
            if result.content:
                # Extract text content from the result
                for item in result.content:
                    if hasattr(item, "text"):
                        result_dict.setdefault("texts", []).append(item.text)
                    elif hasattr(item, "data"):
                        result_dict["data"] = item.data
                # If only one text item, flatten for convenience
                texts = result_dict.get("texts", [])
                if len(texts) == 1 and set(result_dict.keys()) == {"texts"}:
                    try:
                        import json

                        parsed = json.loads(texts[0])
                        result_dict = parsed if isinstance(parsed, dict) else {"text": texts[0]}
                    except (json.JSONDecodeError, ValueError):
                        result_dict = {"text": texts[0]}

            logger.info(
                "MCPStdClient: tool '%s/%s' succeeded",
                server_name or server_url,
                tool_name,
            )
            return MCPToolResult(
                success=True,
                data=result_dict,
                server_name=server_name or server_url,
                tool_name=tool_name,
            )

        except Exception as exc:
            logger.warning(
                "MCPStdClient: tool '%s/%s' failed: %s",
                server_name or server_url,
                tool_name,
                exc,
            )
            return MCPToolResult(
                success=False,
                error=str(exc),
                server_name=server_name or server_url,
                tool_name=tool_name,
            )


# Module-level singleton
mcp_std_client = MCPStdClient()
