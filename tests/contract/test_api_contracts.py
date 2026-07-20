"""API 契约测试 — 验证所有端点响应符合 Schema 定义。

测试环境说明：
- TestClient 无 PG/Redis/Qdrant，路由可能返回 503 fallback。
- 本测试验证响应格式契约（状态码范围 / 字段结构），不验证业务逻辑。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.schemas.response import (  # noqa: E402
    HealthResponse,
    HumanReviewResponse,
    TaskStatusResponse,
)
from app import app  # noqa: E402

client = TestClient(app)


# ── Health endpoint contract ──────────────────────────────────────────


class TestHealthContract:
    """GET /health 契约验证。"""

    def test_status_code_200(self) -> None:
        r = client.get("/health")
        assert r.status_code == 200

    def test_response_matches_schema(self) -> None:
        r = client.get("/health")
        data = r.json()
        parsed = HealthResponse(**data)
        assert parsed.status == "ok"
        assert isinstance(parsed.services, dict)
        assert parsed.version == "0.1.0"

    def test_required_fields_present(self) -> None:
        r = client.get("/health")
        data = r.json()
        for field in ("status", "services", "version"):
            assert field in data, f"Missing required field: {field}"

    def test_response_time_under_100ms(self) -> None:
        """AGENTS.md 硬性要求：/health 必须在 100ms 内响应。"""
        import time

        start = time.perf_counter()
        client.get("/health")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 100, f"Health check took {elapsed_ms:.1f}ms, must be <100ms"


# ── Metrics endpoint contract ─────────────────────────────────────────


class TestMetricsContract:
    """GET /metrics 契约验证。"""

    def test_content_type_is_prometheus(self) -> None:
        r = client.get("/metrics")
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/plain" in ct, f"Expected text/plain, got {ct}"


# ── Chat stream endpoint contract ─────────────────────────────────────


class TestChatStreamContract:
    """POST /chat/stream SSE 契约验证。"""

    def test_sse_content_type(self) -> None:
        r = client.post(
            "/chat/stream",
            json={"query": "测试", "report_type": "deep_report", "user_id": "u1"},
        )
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/event-stream" in ct, f"Expected SSE, got {ct}"

    def test_empty_query_rejected(self) -> None:
        r = client.post(
            "/chat/stream",
            json={"query": "", "report_type": "deep_report"},
        )
        assert r.status_code == 422

    def test_query_too_long_rejected(self) -> None:
        r = client.post(
            "/chat/stream",
            json={"query": "x" * 5001, "report_type": "deep_report"},
        )
        assert r.status_code == 422

    def test_invalid_report_type_rejected(self) -> None:
        r = client.post(
            "/chat/stream",
            json={"query": "test", "report_type": "invalid_type"},
        )
        assert r.status_code == 422

    def test_all_valid_report_types_accepted(self) -> None:
        for rtype in ("deep_report", "flash_news", "earnings_analysis"):
            r = client.post(
                "/chat/stream",
                json={"query": "测试", "report_type": rtype, "user_id": "u1"},
            )
            assert r.status_code == 200, f"report_type={rtype} should be accepted"

    def test_accepts_json_content_type(self) -> None:
        r = client.post(
            "/chat/stream",
            content=json.dumps({"query": "test", "report_type": "deep_report", "user_id": "u1"}),
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 200


# ── Index build endpoint contract ─────────────────────────────────────


class TestIndexBuildContract:
    """POST /index/build 契约验证。

    注意：此端点依赖 Redis。TestClient 环境下 Redis 不可用，
    请求将因基础设施缺失而报错。本测试验证 Pydantic 验证层。
    """

    def test_missing_collection_name_rejected(self) -> None:
        r = client.post(
            "/index/build",
            json={"documents": [{"text": "test"}]},
        )
        assert r.status_code == 422

    def test_missing_documents_rejected(self) -> None:
        r = client.post(
            "/index/build",
            json={"collection_name": "test_coll"},
        )
        assert r.status_code == 422

    def test_empty_collection_name_rejected(self) -> None:
        r = client.post(
            "/index/build",
            json={"collection_name": "", "documents": [{"text": "test"}]},
        )
        assert r.status_code == 422

    def test_index_build_request_schema(self) -> None:
        """验证 IndexBuildRequest schema 存在且字段正确。"""
        from api.routers.index import IndexBuildRequest

        req = IndexBuildRequest(collection_name="test", documents=[{"text": "hello"}])
        assert req.collection_name == "test"
        assert len(req.documents) == 1


# ── Task status endpoint contract ─────────────────────────────────────


class TestTaskStatusContract:
    """GET /task/{workflow_id} 契约验证。"""

    def test_returns_200(self) -> None:
        r = client.get("/task/test-wf-1")
        assert r.status_code == 200

    def test_response_matches_schema(self) -> None:
        r = client.get("/task/test-wf-1")
        data = r.json()
        parsed = TaskStatusResponse(**data)
        assert parsed.workflow_id is not None
        assert isinstance(parsed.status, str)

    def test_required_fields_present(self) -> None:
        r = client.get("/task/test-wf-1")
        data = r.json()
        for field in ("workflow_id", "status", "retry_count", "created_at"):
            assert field in data, f"Missing required field: {field}"


# ── Human review endpoint contract ────────────────────────────────────


class TestHumanReviewContract:
    """POST /task/review 契约验证。

    注意：此端点依赖 PG Checkpointer。TestClient 环境下 checkpointer 为 None，
    请求将返回 503。本测试验证验证层（Pydantic）和契约格式。
    """

    def test_valid_request_returns_expected_status(self) -> None:
        """请求格式正确时返回 200 (PG可用) 或 503 (PG不可用)。"""
        r = client.post(
            "/task/review",
            json={"workflow_id": "wf-contract-1", "decision": "approved"},
        )
        assert r.status_code in (200, 503), f"Expected 200 or 503, got {r.status_code}"

    def test_invalid_decision_rejected(self) -> None:
        r = client.post(
            "/task/review",
            json={"workflow_id": "wf-contract-4", "decision": "maybe_later"},
        )
        assert r.status_code == 422

    def test_missing_workflow_id_rejected(self) -> None:
        r = client.post(
            "/task/review",
            json={"decision": "approved"},
        )
        assert r.status_code == 422

    def test_comment_too_long_rejected(self) -> None:
        r = client.post(
            "/task/review",
            json={"workflow_id": "wf-contract-5", "decision": "approved", "comment": "x" * 1001},
        )
        assert r.status_code == 422

    def test_response_structure_when_available(self) -> None:
        """验证响应结构（503 时检查 error detail 格式）。"""
        r = client.post(
            "/task/review",
            json={"workflow_id": "wf-contract-6", "decision": "approved"},
        )
        data = r.json()
        if r.status_code == 200:
            for field in ("workflow_id", "accepted", "message"):
                assert field in data, f"Missing required field: {field}"
        elif r.status_code == 503:
            assert "detail" in data, "503 should contain detail message"


# ── Error response contract ───────────────────────────────────────────


class TestErrorResponseContract:
    """统一错误响应格式契约。"""

    def test_422_has_detail_field(self) -> None:
        """422 响应必须包含 detail 字段。"""
        r = client.post("/chat/stream", json={"query": "", "report_type": "deep_report"})
        assert r.status_code == 422
        data = r.json()
        assert "detail" in data, "422 response must contain 'detail'"

    def test_404_for_nonexistent_route(self) -> None:
        """不存在的路由返回 404。"""
        r = client.get("/nonexistent-route")
        assert r.status_code == 404
