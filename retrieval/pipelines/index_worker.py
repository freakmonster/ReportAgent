"""异步索引构建 Worker —— 从 Redis Stream 消费 IndexingTask，调用 IndexBuilder 构建索引。

职责：
1. 从 Redis Stream (indexing:tasks) 取出 IndexingTask
2. 调用 IndexBuilder 构建索引（PDF / URL / 纯文本）
3. 更新 Redis Hash 中的任务状态（processing → ready / failed）
4. 构建成功 ACK 消息；构建失败由 IndexBuilder._build() 推送 DLQ 后 ACK
5. 支持单次处理（--once）和持续循环（默认）两种模式

运行方式：
    # 持续运行（生产模式）
    python -m retrieval.pipelines.index_worker

    # 单次处理一条任务后退出（测试/调试用）
    python -m retrieval.pipelines.index_worker --once
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from config.settings import settings
from infrastructure.cache.redis_client import close_redis, get_redis, init_redis
from infrastructure.message_queue.dlq import init_dead_letter_queue
from infrastructure.message_queue.task_queue import (
    TaskQueue,
    init_task_queue,
)

logger = logging.getLogger(__name__)

# 默认 consumer name，多实例部署时可通过环境变量区分
CONSUMER_NAME = "index_worker_1"


class IndexWorker:
    """异步索引构建 Worker。

    作为独立进程运行，持续消费 Redis Stream 中的 IndexingTask，
    调用 IndexBuilder 执行实际的索引构建操作。
    """

    def __init__(self, consumer_name: str = CONSUMER_NAME) -> None:
        self._consumer_name = consumer_name
        self._running = False
        self._queue: TaskQueue | None = None

    async def start(self, *, once: bool = False) -> None:
        """启动 Worker。

        Args:
            once: 如果为 True，处理一条任务后退出；否则持续循环。
        """
        # 初始化基础设施
        await init_redis()
        init_task_queue(get_redis())
        init_dead_letter_queue(get_redis())

        from infrastructure.message_queue.task_queue import _get_queue

        self._queue = _get_queue()

        self._running = True
        mode = "once" if once else "continuous"
        logger.info(f"IndexWorker started | consumer={self._consumer_name} mode={mode}")

        if once:
            await self._process_one()
        else:
            await self._run_loop()

    async def stop(self) -> None:
        """优雅停止 Worker。"""
        self._running = False
        logger.info(f"IndexWorker stopping | consumer={self._consumer_name}")

    async def _run_loop(self) -> None:
        """持续消费循环。"""
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:
                # Windows 不支持 add_signal_handler，用 KeyboardInterrupt
                pass

        consecutive_errors = 0
        max_consecutive_errors = 5

        while self._running:
            try:
                processed = await self._process_one()
                if processed:
                    consecutive_errors = 0
                # 无任务时短暂休眠避免空转
                await asyncio.sleep(0.5)
            except KeyboardInterrupt:
                logger.info("IndexWorker interrupted by user")
                break
            except Exception as exc:
                consecutive_errors += 1
                logger.error(
                    f"IndexWorker loop error | error={exc} consecutive_errors={consecutive_errors}"
                )
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(
                        f"Too many consecutive errors, stopping worker | count={consecutive_errors}"
                    )
                    break
                await asyncio.sleep(min(2**consecutive_errors, 30))

        await close_redis()
        logger.info(f"IndexWorker stopped | consumer={self._consumer_name}")

    async def _process_one(self) -> bool:
        """处理队列中的一条任务。

        Returns:
            True 如果成功处理了一条任务，False 如果没有待处理任务。
        """
        if self._queue is None:
            return False

        result = await self._queue.dequeue(self._consumer_name, block_ms=2000)
        if result is None:
            return False

        message_id, task = result
        logger.info(
            f"IndexWorker processing task | task_id={task.task_id} "
            f"file_type={task.file_type} collection={task.collection_name}"
        )

        # 更新状态为 processing
        await self._queue.update_status(task.task_id, "processing")

        try:
            await self._build_index(task)
            # 构建成功
            await self._queue.update_status(task.task_id, "ready")
            await self._queue.ack(message_id)
            logger.info(
                f"IndexWorker task completed | task_id={task.task_id} "
                f"collection={task.collection_name}"
            )
            return True

        except Exception as exc:
            # IndexBuilder._build() 已推送 DLQ，这里只需更新状态和 ACK
            await self._queue.update_status(task.task_id, "failed", error=str(exc))
            await self._queue.ack(message_id)
            logger.error(f"IndexWorker task failed | task_id={task.task_id} error={exc}")
            return True  # 有处理，只是失败了

    async def _build_index(self, task: Any) -> None:
        """根据任务类型调用 IndexBuilder 构建索引。

        Args:
            task: IndexingTask 实例（含 file_path, file_type, collection_name）。
        """
        from retrieval.embedders.embedding_model import EmbeddingModel
        from retrieval.pipelines.build_index import IndexBuilder
        from retrieval.vectorstores.qdrant_store import QdrantStore

        store = QdrantStore(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key,
        )
        builder = IndexBuilder(
            qdrant_store=store,
            base_collection=task.collection_name,
        )

        file_type = task.file_type.lower()
        file_path = task.file_path

        if file_type == "pdf":
            result = await builder.build_from_pdfs([file_path], incremental=False, use_buffer=True)
        elif file_type == "url":
            result = await builder.build_from_urls([file_path], incremental=False, use_buffer=True)
        elif file_type == "text":
            result = await builder.build_from_texts(
                [file_path],
                sources=[f"text_{task.task_id[:8]}"],
                incremental=False,
                use_buffer=False,
            )
        else:
            raise ValueError(
                f"Unknown file_type '{task.file_type}'. Expected 'pdf', 'url', or 'text'."
            )

        logger.info(
            f"Index build result | task_id={task.task_id} docs={result.doc_count} "
            f"chunks={result.chunk_count} published={result.published}"
        )

        await store.close()


# ── CLI entry point ──────────────────────────────────────────


def main() -> None:
    """CLI 入口：启动异步索引构建 Worker。"""
    import argparse

    parser = argparse.ArgumentParser(description="Async index building worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process a single task and exit (for testing)",
    )
    parser.add_argument(
        "--consumer",
        default=CONSUMER_NAME,
        help=f"Consumer name (default: {CONSUMER_NAME})",
    )
    args = parser.parse_args()

    worker = IndexWorker(consumer_name=args.consumer)

    try:
        asyncio.run(worker.start(once=args.once))
    except KeyboardInterrupt:
        print("\nWorker stopped by user.")


if __name__ == "__main__":
    main()
