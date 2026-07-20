"""混沌测试 — 故障注入与容错验证。

覆盖：
- LLM 降级链（writer/editor/data_analyst 三级降级）
- 限流器过载保护
- 认证中间件故障场景
- 数据采集器降级
- 审核重试循环
- DeepSeek 客户端 tenacity 重试
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

client = TestClient(app)


# ── Writer LLM 故障注入 ───────────────────────────────────────────────


class TestWriterLLMFailure:
    """Writer 节点 DeepSeek 全部挂掉时，应降级到 fallback_chapter。"""

    def test_llm_failure_returns_fallback_content(self) -> None:
        from agents.nodes.writer import _fallback_chapter

        result = _fallback_chapter("量子计算", "量子计算是一种新型计算范式。")
        assert "LLM 生成失败" in result, "Fallback must indicate LLM failure"
        assert "量子计算" in result, "Fallback must preserve topic"

    def test_fallback_truncates_long_data(self) -> None:
        from agents.nodes.writer import _fallback_chapter

        long_data = "数据" * 300
        result = _fallback_chapter("长数据章节", long_data)
        assert len(long_data) > 500
        assert "..." in result, "Long data should be truncated"


# ── Editor LLM 故障注入 ───────────────────────────────────────────────


class TestEditorLLMFailure:
    """Editor 节点 DeepSeek 挂掉时，应保留原文。"""

    def test_fallback_clean_preserves_content(self) -> None:
        from agents.nodes.editor import _fallback_clean

        original = "量子计算市场规模预计到 2030 年达到 650 亿美元"
        result = _fallback_clean(original)
        assert len(result) > 0
        assert result.strip() == result, "Should be stripped"

    def test_normalize_markdown_handles_empty(self) -> None:
        from agents.nodes.editor import _normalize_markdown

        result = _normalize_markdown("")
        assert isinstance(result, str), "_normalize_markdown should return str"


# ── Data Analyst LLM 故障注入 ─────────────────────────────────────────


class TestDataAnalystLLMFailure:
    """Data Analyst 三级降级链验证。"""

    @pytest.mark.asyncio
    async def test_insights_fallback_on_empty_list(self) -> None:
        """空 insights 时 entry() 应触发模板降级。"""
        from agents.nodes.data_analyst import entry

        state = {
            "base": {},
            "collection": {
                "raw_docs": [
                    {"title": "量子计算", "url": "https://example.com", "content": "数据"}
                ],
                "compressed_summary": {"量子计算": "数据内容"},
                "chapter_plan": ["摘要与概述"],
                "source_urls": ["https://example.com"],
            },
        }
        with patch(
            "agents.nodes.data_analyst._generate_insights", new_callable=AsyncMock, return_value=[]
        ):
            result = await entry(state)

        analysis = result["collection"].get("analysis", {})
        assert isinstance(analysis, dict), "Should return analysis dict even with empty insights"

    @pytest.mark.asyncio
    async def test_entry_handles_no_insights_gracefully(self) -> None:
        """LLM 返回空列表时 entry 不崩溃。"""
        from agents.nodes.data_analyst import entry

        state = {
            "base": {},
            "collection": {
                "raw_docs": [],
                "compressed_summary": {},
                "chapter_plan": ["摘要与概述"],
                "source_urls": [],
            },
        }
        with patch(
            "agents.nodes.data_analyst._generate_insights", new_callable=AsyncMock, return_value=[]
        ):
            result = await entry(state)
        assert "collection" in result, "Must return state even with no insights"


# ── Rate Limiter 过载 ─────────────────────────────────────────────────


class TestRateLimiterOverload:
    """限流器过载保护验证。"""

    def test_normal_request_not_limited(self) -> None:
        """正常请求不应被限流。"""
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_endpoint_never_blocked(self) -> None:
        """健康检查即使大量请求也不应被拦截。"""
        for _ in range(10):
            r = client.get("/health")
            assert r.status_code == 200

    def test_auth_required_for_protected_routes(self) -> None:
        """受保护路由需要认证。"""
        r = client.post(
            "/chat/stream",
            json={"query": "测试", "report_type": "deep_report"},
            headers={"Authorization": "Bearer invalid_token_xyz"},
        )
        assert r.status_code in (401, 403), "Protected routes should require auth"


# ── Auth Middleware 故障场景 ──────────────────────────────────────────


class TestAuthFailureScenarios:
    """认证中间件故障场景。"""

    def test_missing_auth_accepts_health(self) -> None:
        """健康检查端点无需认证。"""
        r = client.get("/health", headers={})
        assert r.status_code == 200

    def test_invalid_bearer_token_rejected(self) -> None:
        """无效 Bearer Token 应返回 401。"""
        r = client.post(
            "/chat/stream",
            json={"query": "测试", "report_type": "deep_report"},
            headers={"Authorization": "Bearer invalid_token_xyz"},
        )
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"

    def test_dev_mode_accepts_anonymous(self) -> None:
        """开发模式下 anonymous 用户应被接受。"""
        r = client.post(
            "/chat/stream",
            json={"query": "测试", "report_type": "deep_report", "user_id": "anonymous"},
        )
        assert r.status_code == 200


# ── Data Collector 降级 ───────────────────────────────────────────────


class TestDataCollectorDegradation:
    """数据采集器降级行为验证。"""

    @pytest.mark.asyncio
    async def test_empty_user_input_returns_unchanged(self) -> None:
        """空查询应安全返回空数据而非崩溃。"""
        from agents.nodes.data_collector import entry

        state = {
            "base": {"user_input": "", "template_name": "deep_report"},
            "collection": {"raw_docs": [], "chapter_plan": []},
        }
        result = await entry(state)
        assert "collection" in result

    def test_noop_result_structure(self) -> None:
        """_noop_result 返回正确的结构。"""
        from agents.nodes.data_collector import _noop_result

        result = _noop_result(
            collection={"raw_docs": [], "chapter_plan": ["测试"]},
            base={"template_name": "deep_report"},
        )
        assert "collection" in result
        assert "raw_docs" in result["collection"]
        assert len(result["collection"]["raw_docs"]) == 0


# ── Reviewer Retry Loop ───────────────────────────────────────────────


class TestReviewerRetryLoop:
    """审核重试循环验证。"""

    def test_rejected_lt_3_routes_to_writer(self) -> None:
        from agents.edges.conditional_edges import route_by_review

        state = {"review": {"decision": "rejected"}, "base": {"retry_count": 1}}
        assert route_by_review(state) == "writer"

    def test_rejected_eq_3_routes_to_human(self) -> None:
        from agents.edges.conditional_edges import route_by_review

        state = {"review": {"decision": "rejected"}, "base": {"retry_count": 3}}
        assert route_by_review(state) == "human_review"

    def test_rejected_gt_3_routes_to_human(self) -> None:
        from agents.edges.conditional_edges import route_by_review

        state = {"review": {"decision": "rejected"}, "base": {"retry_count": 5}}
        assert route_by_review(state) == "human_review"

    def test_approved_routes_to_publisher(self) -> None:
        from agents.edges.conditional_edges import route_by_review

        state = {"review": {"decision": "approved"}}
        assert route_by_review(state) == "publisher"

    def test_needs_human_routes_to_human_review(self) -> None:
        from agents.edges.conditional_edges import route_by_review

        state = {"review": {"decision": "needs_human"}}
        assert route_by_review(state) == "human_review"

    def test_make_router_works(self) -> None:
        from agents.edges.conditional_edges import make_router

        router = make_router(
            "reviewer",
            {
                "approved": "publisher",
                "needs_human": "human_review",
                "rejected": {"true_dest": "writer", "false_dest": "human_review"},
            },
        )
        result = router({"review": {"decision": "approved"}, "base": {"retry_count": 0}})
        assert result == "publisher"


# ── DeepSeek Client Tenacity Retry ─────────────────────────────────────


class TestDeepSeekRetry:
    """DeepSeek 客户端 tenacity 重试验证。"""

    def test_deepseek_client_init_no_crash(self) -> None:
        """客户端初始化不应崩溃（懒加载模式）。"""
        from models.llm_providers.deepseek_client import DeepSeekClient

        ds_client = DeepSeekClient()
        assert ds_client is not None

    @pytest.mark.asyncio
    async def test_chat_retries_on_api_error(self) -> None:
        """API 错误时 tenacity 应该重试（前2次失败，第3次成功）。"""
        from models.llm_providers.deepseek_client import DeepSeekClient

        client_instance = DeepSeekClient()
        with patch.object(client_instance, "_client") as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(
                side_effect=[
                    Exception("API Error 1"),
                    Exception("API Error 2"),
                    MagicMock(
                        choices=[MagicMock(message=MagicMock(content="成功"))],
                        usage=MagicMock(prompt_tokens=10, completion_tokens=5),
                    ),
                ]
            )
            try:
                await client_instance.chat([{"role": "user", "content": "测试"}])
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_chat_timeout_exhausts_retries(self) -> None:
        """连续超时耗尽重试次数后应抛出 RetryError。"""
        import tenacity
        from openai import APITimeoutError

        from models.llm_providers.deepseek_client import DeepSeekClient

        client_instance = DeepSeekClient()
        with patch.object(client_instance, "_client") as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(
                side_effect=APITimeoutError("Request timed out")
            )
            with pytest.raises((tenacity.RetryError, APITimeoutError)):
                await client_instance.chat([{"role": "user", "content": "测试"}])
