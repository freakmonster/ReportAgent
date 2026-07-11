"""Reranker 策略接口。所有重排序器必须实现此抽象基类。"""
from abc import ABC, abstractmethod
from typing import Any


class BaseReranker(ABC):
    """重排序器抽象基类。

    实现此接口的类可通过 HybridRetriever 的依赖注入进行插拔，
    由 YAML 配置 `reranker_enabled` 开关控制启用/禁用。
    """

    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """对候选文档列表进行重排序。

        Args:
            query: 原始查询文本。
            candidates: 候选文档列表，每项含 id, text, score 等字段。
            top_k: 返回结果数。

        Returns:
            重排序后的 top_k 结果列表。
        """
        ...
