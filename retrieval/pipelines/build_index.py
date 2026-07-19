"""索引构建管线 —— 批量文档处理 + 增量更新 + V2.1 双缓冲原子切换。

支持：
- 从 PDF/URL 加载文档
- 语义分块
- 批量 Embedding + 入库
- 增量更新（只索引新文档）
- 双缓冲发布（新索引构建完成后原子切换）
"""

from __future__ import annotations

import hashlib
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

from infrastructure.database.repositories.index_repo import IndexStatusRecord, get_index_repo
from infrastructure.message_queue.dlq import push_to_dlq
from infrastructure.observability.logger import get_logger
from retrieval.chunkers.paragraph_chunker import ChunkResult, chunk_text
from retrieval.embedders.embedding_model import EmbeddingModel
from retrieval.loaders.pdf_loader import parse_pdf
from retrieval.loaders.url_loader import WebPage, fetch_url
from retrieval.vectorstores.qdrant_store import QdrantStore

logger = get_logger(__name__)


@dataclass
class IndexProgress:
    """索引构建进度"""
    total_docs: int
    indexed_docs: int
    total_chunks: int
    stage: str = "init"
    error: str | None = None


@dataclass
class DocumentRecord:
    """文档记录"""
    source: str
    content: str
    content_hash: str
    mime_type: str = "text/plain"


@dataclass
class BuildResult:
    """索引构建结果"""
    collection_name: str
    doc_count: int
    chunk_count: int
    buffer_name: str | None = None
    published: bool = False
    errors: list[str] = field(default_factory=list)


def _hash_content(content: str) -> str:
    """计算文档内容哈希（用于增量更新判断）。"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


class IndexBuilder:
    """索引构建器。

    提供同步和异步构建方法，支持：
    - 批量文档处理（PDF/URL 等）
    - 增量更新（基于内容哈希跳过已索引文档）
    - 分块配置
    - 双缓冲发布
    """

    def __init__(
        self,
        qdrant_store: QdrantStore,
        embedder: EmbeddingModel | None = None,
        base_collection: str = "documents",
        target_chunk_tokens: int = 512,
        min_chars: int = 200,
        overlap_tokens: int = 50,
    ) -> None:
        self.store = qdrant_store
        self.embedder = embedder or EmbeddingModel.get_instance()
        self.base_collection = base_collection
        self.target_chunk_tokens = target_chunk_tokens
        self.min_chars = min_chars
        self.overlap_tokens = overlap_tokens
        # 内存字典，服务重启后丢失——增量更新退化为全量更新。
        # 需要持久化时改为 Redis/PostgreSQL 存储。
        self._known_hashes: dict[str, str] = {}

    async def build_from_pdfs(
        self,
        pdf_paths: list[str | Path],
        *,
        incremental: bool = False,
        use_buffer: bool = False,
    ) -> BuildResult:
        """从 PDF 文件列表构建索引。

        Args:
            pdf_paths: PDF 文件路径列表。
            incremental: 是否增量更新（跳过已知内容）。
            use_buffer: 是否使用双缓冲（推荐生产环境使用）。

        Returns:
            BuildResult 含构建统计。
        """
        documents: list[DocumentRecord] = []
        errors: list[str] = []

        for path in pdf_paths:
            path_obj = Path(path)
            source = str(path_obj)
            try:
                pdf_bytes = path_obj.read_bytes()
                doc = parse_pdf(source, pdf_bytes)
                content = doc.full_text
                content_hash = _hash_content(content)
                documents.append(DocumentRecord(
                    source=source,
                    content=content,
                    content_hash=content_hash,
                    mime_type="application/pdf",
                ))
            except ValueError as exc:
                errors.append(f"Skipped {source}: {exc}")
                logger.warning("Skipping PDF", source=source, reason=str(exc))
            except Exception as exc:
                errors.append(f"Failed {source}: {exc}")
                logger.error("Failed to process PDF", source=source, error=str(exc))

        return await self._build(documents, incremental=incremental, use_buffer=use_buffer, errors=errors)

    async def build_from_urls(
        self,
        urls: list[str],
        *,
        incremental: bool = False,
        use_buffer: bool = True,
        max_concurrent: int = 5,
    ) -> BuildResult:
        """从 URL 列表构建索引。

        Args:
            urls: 待抓取的 URL 列表。
            incremental: 是否增量更新。
            use_buffer: 是否使用双缓冲。
            max_concurrent: 最大并发抓取数。

        Returns:
            BuildResult 含构建统计。
        """
        import asyncio

        from retrieval.loaders.url_loader import fetch_multiple

        pages: list[WebPage] = await fetch_multiple(
            urls,
            max_concurrent=max_concurrent,
        )

        # 记录 HTTP 失败的 URL（B1）
        errors: list[str] = []
        success_urls = {page.url for page in pages}
        failed_urls = [u for u in urls if u not in success_urls]
        if failed_urls:
            for u in failed_urls:
                errors.append(f"HTTP fetch failed or no content: {u}")
            logger.warning("Some URLs failed", failed=len(failed_urls), total=len(urls))

        documents: list[DocumentRecord] = []
        errors: list[str] = []

        for page in pages:
            if not page.text:
                errors.append(f"Empty content from {page.url}")
                continue
            content_hash = _hash_content(page.text)
            documents.append(DocumentRecord(
                source=page.url,
                content=page.text,
                content_hash=content_hash,
                mime_type="text/html",
            ))

        return await self._build(documents, incremental=incremental, use_buffer=use_buffer, errors=errors)

    async def build_from_texts(
        self,
        texts: list[str],
        sources: list[str] | None = None,
        *,
        incremental: bool = False,
        use_buffer: bool = False,
    ) -> BuildResult:
        """从纯文本列表构建索引。

        Args:
            texts: 文本内容列表。
            sources: 来源标识列表（如果为 None 则使用索引号）。
            incremental: 是否增量更新。
            use_buffer: 是否使用双缓冲。

        Returns:
            BuildResult 含构建统计。
        """
        if sources is None:
            sources = [f"text_{i:04d}" for i in range(len(texts))]

        documents: list[DocumentRecord] = []
        for source, text in zip(sources, texts):
            content_hash = _hash_content(text)
            documents.append(DocumentRecord(
                source=source,
                content=text,
                content_hash=content_hash,
                mime_type="text/plain",
            ))

        return await self._build(documents, incremental=incremental, use_buffer=use_buffer, errors=[])

    async def _build(
        self,
        documents: list[DocumentRecord],
        *,
        incremental: bool,
        use_buffer: bool,
        errors: list[str],
    ) -> BuildResult:
        """核心构建逻辑。"""
        if not documents:
            return BuildResult(
                collection_name=self.base_collection,
                doc_count=0,
                chunk_count=0,
                errors=errors,
            )

        # 增量过滤
        if incremental:
            new_docs: list[DocumentRecord] = []
            skipped = 0
            for doc in documents:
                if doc.content_hash in self._known_hashes:
                    skipped += 1
                else:
                    new_docs.append(doc)
                    self._known_hashes[doc.content_hash] = doc.source
            if skipped > 0:
                logger.info("Incremental skip", skipped=skipped, remaining=len(new_docs))
            documents = new_docs
        else:
            for doc in documents:
                self._known_hashes[doc.content_hash] = doc.source

        if not documents:
            # 空结果无需记录 index_status
            return BuildResult(
                collection_name=self.base_collection,
                doc_count=0,
                chunk_count=0,
                published=False,
                errors=errors,
            )

        try:
            # 分块
            chunk_results: list[ChunkResult] = []
            for doc in documents:
                result = chunk_text(
                    doc.content,
                    source=doc.source,
                    target_chunk_tokens=self.target_chunk_tokens,
                    min_chars=self.min_chars,
                    overlap_tokens=self.overlap_tokens,
                )
                chunk_results.append(result)

            total_chunks = sum(r.total_chunks for r in chunk_results)

            # 收集所有 chunks
            all_texts: list[str] = []
            all_sources: list[str] = []
            for result in chunk_results:
                for chunk in result.chunks:
                    all_texts.append(chunk.text)
                    all_sources.append(result.source)

            # 决定目标 collection
            if use_buffer:
                target_collection = await self.store.create_buffer(self.base_collection)
            else:
                target_collection = self.base_collection
                await self.store.create_collection(target_collection)

            # 批量 Embedding + 入库
            await self.store.upsert(
                collection=target_collection,
                texts=all_texts,
                metas=[{"source": src, "chunk_index": i} for i, src in enumerate(all_sources)],
                embedder=self.embedder,
            )

            published = False
            if use_buffer:
                await self.store.promote_buffer(target_collection, self.base_collection)
                published = True
                logger.info("Buffer promoted successfully", buffer=target_collection, active=self.base_collection)

            result = BuildResult(
                collection_name=self.base_collection,
                doc_count=len(documents),
                chunk_count=total_chunks,
                buffer_name=target_collection if use_buffer else None,
                published=published,
                errors=errors,
            )
            logger.info(
                "Index build completed",
                docs=result.doc_count,
                chunks=result.chunk_count,
                published=result.published,
            )

            # ── 记录构建成功到 index_status ─────────────────────────
            try:
                checksum = hashlib.sha256(
                    "|".join(sorted(d.content_hash for d in documents)).encode()
                ).hexdigest()
                await get_index_repo().mark_ready(
                    collection_name=self.base_collection,
                    document_count=len(documents),
                    checksum=checksum,
                )
            except Exception as repo_exc:
                logger.warning("Failed to record index build status", error=str(repo_exc))

            return result

        except Exception as exc:
            logger.error("Index build failed", error=str(exc))

            # ── 记录构建失败到 index_status ─────────────────────────
            try:
                await get_index_repo().mark_failed(
                    collection_name=self.base_collection,
                    error_msg=str(exc),
                )
            except Exception as repo_exc:
                logger.warning("Failed to record index build failure", error=str(repo_exc))

            # ── 推送失败消息到 Dead Letter Queue ────────────────────
            try:
                payload = {
                    "doc_count": len(documents),
                    "incremental": incremental,
                    "use_buffer": use_buffer,
                    "error_count": len(errors),
                }
                await push_to_dlq(
                    collection_name=self.base_collection,
                    error_traceback=traceback.format_exc(),
                    payload=payload,
                )
            except Exception as dlq_exc:
                logger.warning("Failed to push to DLQ", error=str(dlq_exc))

            raise

    async def incremental_update(
        self,
        new_documents: list[DocumentRecord],
    ) -> BuildResult:
        """增量更新索引（直接写入 active collection，不使用双缓冲）。"""
        if not new_documents:
            return BuildResult(collection_name=self.base_collection, doc_count=0, chunk_count=0)

        # 分块 + 入库
        chunk_results: list[ChunkResult] = []
        for doc in new_documents:
            result = chunk_text(
                doc.content,
                source=doc.source,
                target_chunk_tokens=self.target_chunk_tokens,
                min_chars=self.min_chars,
                overlap_tokens=self.overlap_tokens,
            )
            chunk_results.append(result)

        all_texts: list[str] = []
        all_sources: list[str] = []
        for result in chunk_results:
            for chunk in result.chunks:
                all_texts.append(chunk.text)
                all_sources.append(result.source)

        if all_texts:
            await self.store.upsert(
                collection=self.base_collection,
                texts=all_texts,
                metas=[{"source": src, "chunk_index": i} for i, src in enumerate(all_sources)],
                embedder=self.embedder,
            )

        for doc in new_documents:
            self._known_hashes[doc.content_hash] = doc.source

        result = BuildResult(
            collection_name=self.base_collection,
            doc_count=len(new_documents),
            chunk_count=sum(r.total_chunks for r in chunk_results),
            published=True,
        )
        logger.info("Incremental update completed", docs=result.doc_count, chunks=result.chunk_count)
        return result
