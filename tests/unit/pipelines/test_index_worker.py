"""index_worker 单元测试 —— 使用 mock 验证 Worker 逻辑，不依赖 Redis/Qdrant。"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from infrastructure.message_queue.task_queue import IndexingTask

# ── patch targets: IndexBuilder/QdrantStore are lazy-imported in _build_index()
_PATCH_BUILDER = "retrieval.pipelines.build_index.IndexBuilder"
_PATCH_STORE = "retrieval.vectorstores.qdrant_store.QdrantStore"
_PATCH_EMBED = "retrieval.embedders.embedding_model.EmbeddingModel"


def _make_build_result(**kw):
    """Helper: create a mock BuildResult."""
    defaults = {"doc_count": 1, "chunk_count": 1, "published": False, "buffer_name": None, "errors": []}
    defaults.update(kw)
    return MagicMock(**{k: kw.get(k, defaults[k]) for k in defaults})


class TestIndexWorkerProcessOne:
    """测试 IndexWorker._process_one 核心逻辑。"""

    @pytest.fixture
    def mock_queue(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def mock_store(self) -> AsyncMock:
        m = MagicMock()
        m.close = AsyncMock()
        return m

    @pytest.fixture
    def worker(self, mock_queue: AsyncMock) -> "IndexWorker":
        from retrieval.pipelines.index_worker import IndexWorker
        w = IndexWorker(consumer_name="test_worker")
        w._queue = mock_queue
        w._running = True
        return w

    @pytest.mark.asyncio
    async def test_no_pending_tasks(self, worker: "IndexWorker", mock_queue: AsyncMock) -> None:
        """队列为空时返回 False。"""
        mock_queue.dequeue.return_value = None
        result = await worker._process_one()
        assert result is False
        mock_queue.dequeue.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_text_task_success(
        self, worker: "IndexWorker", mock_queue: AsyncMock, mock_store: AsyncMock,
    ) -> None:
        """text 类型任务 → 状态 ready + ACK。"""
        task = IndexingTask(
            task_id="test-001", file_path="量子计算是新型计算范式。",
            file_type="text", collection_name="test_coll",
        )
        mock_queue.dequeue.return_value = ("msg-1", task)

        with patch(_PATCH_STORE, return_value=mock_store), \
             patch(_PATCH_BUILDER) as mock_builder_cls, \
             patch(_PATCH_EMBED):
            mock_builder = MagicMock()
            mock_builder.build_from_texts = AsyncMock(return_value=_make_build_result())
            mock_builder_cls.return_value = mock_builder

            result = await worker._process_one()

        assert result is True
        mock_queue.update_status.assert_any_call("test-001", "processing")
        mock_queue.update_status.assert_any_call("test-001", "ready")
        mock_queue.ack.assert_called_once_with("msg-1")

    @pytest.mark.asyncio
    async def test_process_task_failure(
        self, worker: "IndexWorker", mock_queue: AsyncMock, mock_store: AsyncMock,
    ) -> None:
        """pdf 构建失败 → 状态 failed + ACK。"""
        task = IndexingTask(
            task_id="test-002", file_path="bad.pdf",
            file_type="pdf", collection_name="test_coll",
        )
        mock_queue.dequeue.return_value = ("msg-2", task)

        with patch(_PATCH_STORE, return_value=mock_store), \
             patch(_PATCH_BUILDER) as mock_builder_cls, \
             patch(_PATCH_EMBED):
            mock_builder = MagicMock()
            mock_builder.build_from_pdfs = AsyncMock(
                side_effect=RuntimeError("PDF parsing failed")
            )
            mock_builder_cls.return_value = mock_builder

            result = await worker._process_one()

        assert result is True
        mock_queue.update_status.assert_any_call("test-002", "processing")
        mock_queue.update_status.assert_any_call("test-002", "failed", error="PDF parsing failed")
        mock_queue.ack.assert_called_once_with("msg-2")

    @pytest.mark.asyncio
    async def test_process_url_task(
        self, worker: "IndexWorker", mock_queue: AsyncMock, mock_store: AsyncMock,
    ) -> None:
        """url 类型任务 → 状态 ready + ACK。"""
        task = IndexingTask(
            task_id="test-003", file_path="https://example.com",
            file_type="url", collection_name="test_coll",
        )
        mock_queue.dequeue.return_value = ("msg-3", task)

        with patch(_PATCH_STORE, return_value=mock_store), \
             patch(_PATCH_BUILDER) as mock_builder_cls, \
             patch(_PATCH_EMBED):
            mock_builder = MagicMock()
            mock_builder.build_from_urls = AsyncMock(return_value=_make_build_result())
            mock_builder_cls.return_value = mock_builder

            result = await worker._process_one()

        assert result is True
        mock_queue.ack.assert_called_once_with("msg-3")

    @pytest.mark.asyncio
    async def test_unknown_file_type_raises(
        self, worker: "IndexWorker", mock_queue: AsyncMock, mock_store: AsyncMock,
    ) -> None:
        """未知 file_type → ValueError → 状态 failed + ACK。"""
        task = IndexingTask(
            task_id="test-004", file_path="f.xyz",
            file_type="image", collection_name="test_coll",
        )
        mock_queue.dequeue.return_value = ("msg-4", task)

        with patch(_PATCH_STORE, return_value=mock_store), \
             patch(_PATCH_BUILDER), \
             patch(_PATCH_EMBED):
            result = await worker._process_one()

        assert result is True
        all_calls = mock_queue.update_status.call_args_list
        has_failed = any(
            c.args[0] == "test-004" and "failed" in str(c.args)
            for c in all_calls
        )
        assert has_failed, f"Expected update_status with 'failed', got {all_calls}"
        mock_queue.ack.assert_called_once_with("msg-4")


class TestIndexWorkerStart:
    """测试 IndexWorker.start 生命周期。"""

    @pytest.mark.asyncio
    async def test_start_once_mode(self) -> None:
        """--once 模式：调用 _process_one 一次后退出。"""
        from retrieval.pipelines.index_worker import IndexWorker

        worker = IndexWorker(consumer_name="test_once")

        with patch("retrieval.pipelines.index_worker.init_redis", new_callable=AsyncMock), \
             patch("retrieval.pipelines.index_worker.get_redis", return_value=MagicMock()), \
             patch("retrieval.pipelines.index_worker.init_task_queue"), \
             patch("retrieval.pipelines.index_worker.init_dead_letter_queue"), \
             patch("infrastructure.message_queue.task_queue._get_queue", return_value=MagicMock()), \
             patch.object(worker, "_process_one", new_callable=AsyncMock, return_value=True) as mock_process:
            await worker.start(once=True)

        mock_process.assert_called_once()
