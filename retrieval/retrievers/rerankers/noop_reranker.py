"""No-Op 重排序器 —— 空转直通实现。默认配置，零开销。"""

from typing import Any

from .base import BaseReranker


class NoOpReranker(BaseReranker):
    """空转重排序器：直接返回前 top_k 条候选，不修改顺序。"""

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """直接返回原候选列表前 top_k 条。"""
        return candidates[:top_k]
