"""Reranker 工厂 — 根据配置返回 NoOp 或 CrossEncoder 重排序器。"""

from config.settings import settings

from .base import BaseReranker
from .noop_reranker import NoOpReranker
from .cross_encoder_reranker import CrossEncoderReranker


def get_reranker() -> BaseReranker:
    """根据 YAML 配置 `reranker_enabled` 返回对应的重排序器实例。

    Returns:
        - NoOpReranker (reranker_enabled=false)：直通，零开销
        - CrossEncoderReranker (reranker_enabled=true)：加载 bge-reranker-v2-m3
    """
    if getattr(settings, "reranker_enabled", False):
        model_name = getattr(settings, "reranker_model", "BAAI/bge-reranker-v2-m3")
        return CrossEncoderReranker(model_name=model_name)
    return NoOpReranker()
