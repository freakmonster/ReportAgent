"""bge-m3 Embedding 模型封装 —— 多语言支持，batch 处理。"""

from __future__ import annotations

from typing import Any

import numpy as np


class EmbeddingModel:
    """bge-m3 Embedding 模型封装。

    采用懒加载单例模式，首次使用时才加载模型到内存。

    Usage:
        model = EmbeddingModel.get_instance()
        vectors = model.embed(["文本1", "文本2"])
    """

    _instance: "EmbeddingModel | None" = None
    _model: Any = None
    _model_name: str = "bge-m3"
    _dimension: int = 1024
    _device: str = "cpu"

    def __init__(self) -> None:
        raise RuntimeError("Use EmbeddingModel.get_instance() instead")

    @classmethod
    def get_instance(
        cls,
        model_name: str = "bge-m3",
        device: str = "cpu",
    ) -> "EmbeddingModel":
        """获取单例实例（懒加载）。

        Args:
            model_name: HuggingFace 模型名，默认 bge-m3。
            device: 推理设备，cpu 或 cuda。

        Returns:
            EmbeddingModel 单例。
        """
        if cls._instance is not None:
            if cls._instance._model_name != model_name or cls._instance._device != device:
                raise RuntimeError(
                    f"EmbeddingModel singleton already initialized with "
                    f"model={cls._instance._model_name}, device={cls._instance._device}. "
                    f"Cannot re-initialize with model={model_name}, device={device}. "
                    f"Call EmbeddingModel.reset_instance() first if you need to change parameters."
                )
            return cls._instance

        cls._instance = object.__new__(cls)
        cls._instance._model_name = model_name
        cls._instance._device = device
        cls._instance._model = None
        return cls._instance

    def _ensure_loaded(self) -> None:
        """懒加载模型。"""
        if self._model is not None:
            return

        from infrastructure.observability.logger import get_logger
        logger = get_logger(__name__)

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for embeddings. "
                "Install with: pip install sentence-transformers"
            )

        logger.info("Loading embedding model", model=self._model_name, device=self._device)
        self._model = SentenceTransformer(self._model_name, device=self._device)
        self._dimension = self._model.get_sentence_embedding_dimension()
        logger.info("Embedding model loaded", dimension=self._dimension)

    @property
    def dimension(self) -> int:
        """获取向量维度。"""
        self._ensure_loaded()
        return self._dimension

    def embed(self, texts: list[str], *, batch_size: int = 32) -> list[list[float]]:
        """将文本列表编码为向量。

        Args:
            texts: 文本列表。
            batch_size: 批量处理大小。

        Returns:
            向量列表，每个向量长度为 dimension。
        """
        if not texts:
            return []

        self._ensure_loaded()

        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings = self._model.encode(
                batch,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            #确保返回 list[float] 列表
            if isinstance(embeddings, np.ndarray):
                vectors.extend(embeddings.tolist())
            else:
                vectors.extend(list(embeddings))

        return vectors

    def embed_single(self, text: str) -> list[float]:
        """编码单个文本。"""
        return self.embed([text])[0]

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（主要用于测试）。"""
        cls._instance = None


def get_embedding_model(
    model_name: str = "bge-m3",
    device: str = "cpu",
) -> EmbeddingModel:
    """获取 Embedding 模型实例的便捷函数。"""
    return EmbeddingModel.get_instance(model_name=model_name, device=device)
