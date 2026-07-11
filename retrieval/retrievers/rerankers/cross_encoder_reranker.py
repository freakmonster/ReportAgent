"""Cross-Encoder 重排序器 —— 基于 bge-reranker-v2-m3。

仅在 `reranker_enabled: true` 时由工厂函数创建。
模型懒加载，首次调用 `rerank()` 时才加载到内存。
"""
from __future__ import annotations

from typing import Any

from infrastructure.observability.logger import get_logger
from .base import BaseReranker

logger = get_logger(__name__)


class CrossEncoderReranker(BaseReranker):
    """Cross-Encoder 重排序器。

    使用 BAAI/bge-reranker-v2-m3 模型对候选文档做细粒度相关性评分。
    模型在首次调用时懒加载，避免启动时占用内存。
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3") -> None:
        self._model_name = model_name
        self._model: Any = None
        self._device: str = "cpu"

    def _ensure_loaded(self) -> None:
        """懒加载 Cross-Encoder 模型。"""
        if self._model is not None:
            return

        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for reranker. "
                "Install with: pip install sentence-transformers"
            )

        logger.info("Loading reranker model", model=self._model_name)
        self._model = CrossEncoder(self._model_name)
        logger.info("Reranker model loaded", model=self._model_name)

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """对候选文档做 Cross-Encoder 重排序。

        Args:
            query: 原始查询文本。
            candidates: 候选文档列表。
            top_k: 返回结果数。

        Returns:
            重排序后的 top_k 结果。
        """
        if not candidates:
            return []

        self._ensure_loaded()

        # 构造 [query, doc_text] 对
        pairs = [(query, c["text"]) for c in candidates]

        # Cross-Encoder 评分（非异步，在 async 方法中调用 CPU-bound 操作）
        try:
            scores = self._model.predict(pairs, show_progress_bar=False)  # type: ignore[union-attr]
        except Exception as exc:
            logger.error("Reranker prediction failed", error=str(exc))
            # 降级：不改变排序
            return candidates[:top_k]

        # 按分数重排
        scored = list(zip(candidates, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for candidate, score in scored[:top_k]:
            candidate["rerank_score"] = float(score)
            results.append(candidate)

        logger.debug("Reranker completed", candidates=len(candidates), top_k=top_k)
        return results
