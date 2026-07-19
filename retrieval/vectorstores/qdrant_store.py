"""Qdrant 向量存储封装 —— 多租户隔离 + V2.1 双缓冲 Collection 支持。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from infrastructure.observability.logger import get_logger
from retrieval.embedders.embedding_model import EmbeddingModel

logger = get_logger(__name__)


class QdrantStore:
    """Qdrant 向量存储封装。

    - collection_prefix 实现多租户隔离
    - 双缓冲机制：新索引写入带时间戳的 Collection，构建完成后原子切换
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        api_key: str | None = None,
        collection_prefix: str = "research_agent",
        embedding_dimension: int = 768,
    ) -> None:
        self._host = host
        self._port = port
        self._api_key = api_key
        self._collection_prefix = collection_prefix
        self._dimension = embedding_dimension
        self._client: AsyncQdrantClient | None = None

    async def _get_client(self) -> AsyncQdrantClient:
        """懒加载获取 Qdrant 异步客户端。"""
        if self._client is None:
            self._client = AsyncQdrantClient(
                host=self._host,
                port=self._port,
                api_key=self._api_key,
                timeout=30.0,
            )
        return self._client

    def _collection_name(self, name: str) -> str:
        """生成带前缀的 Collection 名。"""
        return f"{self._collection_prefix}_{name}"

    # ── Collection 管理 ──────────────────────────────────────────

    async def create_collection(
        self,
        name: str,
        *,
        distance: str = "Cosine",
    ) -> bool:
        """创建 Collection（如果不存在）。

        Args:
            name: Collection 名称（不带前缀）。
            distance: 距离度量（Cosine / Euclid / Dot）。

        Returns:
            True 如果创建成功或已存在。
        """
        client = await self._get_client()
        collection_name = self._collection_name(name)

        # Use stored dimension if already known, otherwise detect from embedder
        if self._dimension <= 0:
            self._dimension = EmbeddingModel.get_instance().dimension
        try:
            await client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=self._dimension,
                    distance=distance,
                ),
            )
            logger.info("Collection created", name=collection_name, dimension=self._dimension)
            return True
        except Exception as exc:
            if "already exists" in str(exc).lower() or "409" in str(exc):
                logger.debug("Collection already exists", name=collection_name)
                return True
            logger.error("Failed to create collection", name=collection_name, error=str(exc))
            raise

    async def collection_exists(self, name: str) -> bool:
        """检查 Collection 是否存在。"""
        client = await self._get_client()
        try:
            collections = await client.get_collections()
            full_name = self._collection_name(name)
            return any(c.name == full_name for c in collections.collections)
        except Exception:
            return False

    async def delete_collection(self, name: str) -> bool:
        """删除 Collection。"""
        client = await self._get_client()
        collection_name = self._collection_name(name)
        try:
            result = await client.delete_collection(collection_name)
            logger.info("Collection deleted", name=collection_name)
            return result
        except UnexpectedResponse:
            logger.warning("Collection not found for deletion", name=collection_name)
            return False

    async def collection_info(self, name: str) -> dict[str, Any]:
        """获取 Collection 信息。"""
        client = await self._get_client()
        collection_name = self._collection_name(name)
        info = await client.get_collection(collection_name)
        return {
            "name": info.name,
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
        }

    # ── 向量操作 ────────────────────────────────────────────────

    async def upsert(
        self,
        collection: str,
        texts: list[str],
        metas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
        embedder: EmbeddingModel | None = None,
    ) -> list[str]:
        """插入/更新向量。

        Args:
            collection: Collection 名称。
            texts: 文本列表。
            metas: 元数据列表（与 texts 等长）。
            ids: 自定义 ID 列表（默认 UUID v4）。
            embedder: Embedding 模型实例。

        Returns:
            插入的点 ID 列表。
        """
        if not texts:
            return []

        client = await self._get_client()
        collection_name = self._collection_name(collection)

        if embedder is None:
            embedder = EmbeddingModel.get_instance()

        vectors = embedder.embed(texts)

        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]

        if metas is None:
            metas = [{} for _ in texts]

        points = [
            models.PointStruct(
                id=id_,
                vector=vector,
                payload={"text": text, **meta},
            )
            for id_, vector, text, meta in zip(ids, vectors, texts, metas)
        ]

        await client.upsert(
            collection_name=collection_name,
            points=points,
        )
        logger.debug("Points upserted", collection=collection_name, count=len(points))
        return ids

    async def search(
        self,
        collection: str,
        query: str,
        *,
        limit: int = 10,
        score_threshold: float | None = None,
        embedder: EmbeddingModel | None = None,
    ) -> list[dict[str, Any]]:
        """语义搜索。

        Args:
            collection: Collection 名称。
            query: 查询文本。
            limit: 返回结果数。
            score_threshold: 最低分数阈值。
            embedder: Embedding 模型实例。

        Returns:
            搜索结果列表：[{id, text, score, payload}, ...]。
        """
        client = await self._get_client()
        collection_name = self._collection_name(collection)

        if embedder is None:
            embedder = EmbeddingModel.get_instance()

        query_vector = embedder.embed_single(query)

        results = await client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )

        return [
            {
                "id": hit.id,
                "text": hit.payload.get("text", ""),
                "score": hit.score,
                "payload": {k: v for k, v in hit.payload.items() if k != "text"},
            }
            for hit in results.points
        ]

    async def search_batch(
        self,
        collection: str,
        queries: list[str],
        *,
        limit: int = 10,
        embedder: EmbeddingModel | None = None,
    ) -> list[list[dict[str, Any]]]:
        """批量语义搜索。

        Args:
            collection: Collection 名称。
            queries: 查询文本列表。
            limit: 每个查询返回结果数。
            embedder: Embedding 模型实例。

        Returns:
            每个查询的搜索结果列表。
        """
        client = await self._get_client()
        collection_name = self._collection_name(collection)

        if embedder is None:
            embedder = EmbeddingModel.get_instance()

        query_vectors = embedder.embed(queries)

        search_queries = [
            models.SearchRequest(
                vector=qv,
                limit=limit,
                with_payload=True,
            )
            for qv in query_vectors
        ]

        results = await client.search_batch(
            collection_name=collection_name,
            requests=search_queries,
        )

        return [
            [
                {
                    "id": hit.id,
                    "text": hit.payload.get("text", ""),
                    "score": hit.score,
                    "payload": {k: v for k, v in hit.payload.items() if k != "text"},
                }
                for hit in batch
            ]
            for batch in results
        ]

    # ── 按 ID 获取 Point Payload ──────────────────────────────

    async def get_points(
        self,
        collection: str,
        point_ids: list[str],
    ) -> list[dict[str, Any]]:
        """按 ID 批量获取 Point 的 payload。

        Args:
            collection: Collection 名称。
            point_ids: Point ID 列表。

        Returns:
            [{id, payload: {source, chunk_index, ...}}, ...]。
        """
        if not point_ids:
            return []
        client = await self._get_client()
        collection_name = self._collection_name(collection)
        results = await client.retrieve(
            collection_name=collection_name,
            ids=point_ids,
            with_payload=True,
        )
        return [
            {
                "id": pt.id,
                "payload": {k: v for k, v in (pt.payload or {}).items()},
            }
            for pt in results
        ]

    # ── V2.1 双缓冲 ────────────────────────────────────────────

    def _make_buffer_name(self, base_name: str) -> str:
        """生成带时间戳的双缓冲 Collection 名。"""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{base_name}_v{ts}"

    async def create_buffer(self, base_name: str) -> str:
        """创建双缓冲 Collection（新数据写入此缓冲区）。"""
        buffer_name = self._make_buffer_name(base_name)
        await self.create_collection(buffer_name)
        logger.info("Buffer collection created", buffer=buffer_name, base=base_name)
        return buffer_name

    async def promote_buffer(
        self,
        buffer_name: str,
        active_name: str,
    ) -> None:
        """将缓冲区安全提升为活跃 Collection（三步 swap 避免竞态）。

        策略：先重命名 buffer 到临时名 → 删除旧 active → 临时名改为最终名。
        任意步骤崩溃后，恢复只需删除残留的 _swap_ 临时 collection。
        """
        client = await self._get_client()
        full_active = self._collection_name(active_name)
        full_buffer = self._collection_name(buffer_name)

        # 1. 将 buffer 重命名为临时名（不碰 active）
        tmp_name = f"{active_name}_swap_{uuid.uuid4().hex[:8]}"
        full_tmp = self._collection_name(tmp_name)

        try:
            await client.update_collection(
                collection_name=full_buffer,
                deprecated_new_collection_name=full_tmp,
            )
            logger.info("Buffer renamed to tmp", buffer=buffer_name, tmp=tmp_name)
        except Exception:
            logger.error("Failed to rename buffer to tmp", buffer=buffer_name, exc_info=True)
            raise

        # 2. 删除旧 active
        await self.delete_collection(active_name)

        # 3. 将临时名改为正式 active 名
        try:
            await client.update_collection(
                collection_name=full_tmp,
                deprecated_new_collection_name=full_active,
            )
            logger.info("Buffer promoted successfully", buffer=buffer_name, active=active_name)
        except Exception:
            logger.error(
                "Failed to rename tmp to active — recovery: delete collection %s",
                tmp_name,
                exc_info=True,
            )
            raise

    async def close(self) -> None:
        """关闭客户端连接。"""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.debug("Qdrant client closed")
