"""Embedding 模型封装 —— 支持 sentence-transformers / fastembed 双后端。

后端选择通过 config/environments/*.yaml 中的 embedding_backend 配置控制：
  - "sentence_transformers": 基于 PyTorch，支持任意 HuggingFace/本地模型（默认）
  - "fastembed": 基于 ONNX Runtime，零 PyTorch 依赖，仅支持 fastembed 内置模型列表
"""

from __future__ import annotations

from typing import Any

import numpy as np

from infrastructure.observability.logger import get_logger

logger = get_logger(__name__)


class EmbeddingModel:
    """Embedding 模型封装（单例）。

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
    _backend: str = "sentence_transformers"

    def __init__(self) -> None:
        raise RuntimeError("Use EmbeddingModel.get_instance() instead")

    @classmethod
    def get_instance(
        cls,
        model_name: str | None = None,
        device: str = "cpu",
        backend: str | None = None,
    ) -> "EmbeddingModel":
        """获取单例实例（懒加载）。

        Args:
            model_name: 模型名或本地路径。默认读取 settings.embedding_model。
            device: 推理设备，cpu 或 cuda（仅 sentence_transformers 后端生效）。
            backend: "sentence_transformers" 或 "fastembed"。默认读取 settings.embedding_backend。

        Returns:
            EmbeddingModel 单例。
        """
        if model_name is None:
            from config.settings import settings
            model_name = settings.embedding_model
        if backend is None:
            from config.settings import settings
            backend = getattr(settings, "embedding_backend", "sentence_transformers")
        if backend not in ("sentence_transformers", "fastembed"):
            raise ValueError(
                f"Invalid backend '{backend}'. Expected 'sentence_transformers' or 'fastembed'."
            )

        if cls._instance is not None:
            if (
                cls._instance._model_name != model_name
                or cls._instance._device != device
                or cls._instance._backend != backend
            ):
                raise RuntimeError(
                    f"EmbeddingModel singleton already initialized with "
                    f"model={cls._instance._model_name}, device={cls._instance._device}, "
                    f"backend={cls._instance._backend}. "
                    f"Cannot re-initialize with model={model_name}, device={device}, "
                    f"backend={backend}. "
                    f"Call EmbeddingModel.reset_instance() first if you need to change parameters."
                )
            return cls._instance

        cls._instance = object.__new__(cls)
        cls._instance._model_name = model_name
        cls._instance._device = device
        cls._instance._backend = backend
        cls._instance._model = None
        return cls._instance

    @property
    def backend(self) -> str:
        """当前使用的后端。"""
        return self._backend

    def _ensure_loaded(self) -> None:
        """懒加载模型（根据后端类型分发）。"""
        if self._model is not None:
            return

        if self._backend == "fastembed":
            self._ensure_loaded_fastembed()
        else:
            self._ensure_loaded_sentence_transformers()

    def _ensure_loaded_sentence_transformers(self) -> None:
        """使用 sentence-transformers 加载模型。"""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for embeddings. "
                "Install with: pip install sentence-transformers"
            )

        logger.info("Loading embedding model (sentence_transformers)", model=self._model_name, device=self._device)
        self._model = SentenceTransformer(self._model_name, device=self._device)
        # get_sentence_embedding_dimension() → get_embedding_dimension() (v3.0+)
        self._dimension = (
            self._model.get_embedding_dimension()
            if hasattr(self._model, "get_embedding_dimension")
            else self._model.get_sentence_embedding_dimension()
        )
        logger.info("Embedding model loaded", dimension=self._dimension, backend="sentence_transformers")

    def _ensure_loaded_fastembed(self) -> None:
        """使用 fastembed 加载模型。"""
        try:
            from fastembed import TextEmbedding
        except ImportError:
            raise ImportError(
                "fastembed is required for embeddings. "
                "Install with: pip install fastembed"
            )

        logger.info("Loading embedding model (fastembed)", model=self._model_name)

        # fastembed 支持本地路径：通过 specific_model_path 参数
        import os
        if os.path.isdir(self._model_name):
            # 本地路径：使用默认模型名但指定本地路径
            # fastembed 需要知道模型架构，所以用 model_name 指定架构，specific_model_path 指定路径
            # 对于本地 GTE 模型，尝试推断模型类型
            model_arch = self._infer_fastembed_arch(self._model_name)
            self._model = TextEmbedding(
                model_name=model_arch,
                specific_model_path=self._model_name,
            )
        else:
            self._model = TextEmbedding(model_name=self._model_name)

        # 获取维度（从模型属性或首次推理获取）
        try:
            test_vec = list(self._model.embed(["test"]))[0]
            self._dimension = int(test_vec.shape[0])
        except Exception:
            # 回退：从 fastembed 内置模型表中查找维度
            try:
                supported = TextEmbedding.list_supported_models()
                for m in supported:
                    if m["model"] == self._model_name:
                        self._dimension = m["dim"]
                        break
                else:
                    self._dimension = 512  # 默认值
            except Exception:
                self._dimension = 512

        logger.info("Embedding model loaded", dimension=self._dimension, backend="fastembed")

    @staticmethod
    def _infer_fastembed_arch(local_path: str) -> str:
        """从本地路径推断 fastembed 支持的模型架构名。"""
        import os
        path_lower = local_path.lower().replace("\\", "/")

        # 常见中文模型映射
        if "gte" in path_lower and "large" in path_lower:
            return "thenlper/gte-large"
        if "bge-m3" in path_lower:
            return "BAAI/bge-m3"
        if "bge-small-zh" in path_lower:
            return "BAAI/bge-small-zh-v1.5"
        if "bge-base-zh" in path_lower:
            return "BAAI/bge-base-zh-v1.5"
        if "bge-large-zh" in path_lower:
            return "BAAI/bge-large-zh-v1.5"

        # 通用回退：检查 config.json 中的模型架构
        config_path = os.path.join(local_path, "config.json")
        if os.path.exists(config_path):
            import json
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                architectures = config.get("architectures", [])
                model_type = config.get("model_type", "")
                if "Bert" in str(architectures) or "bert" in model_type:
                    return "BAAI/bge-small-zh-v1.5"
            except Exception:
                pass

        # 最终回退 — 可能无法匹配本地模型架构，建议用 sentence_transformers 后端
        logger.warning(
            "Cannot infer fastembed model architecture from local path, falling back to bge-small-zh-v1.5. "
            "Consider using embedding_backend='sentence_transformers' for custom local models.",
            local_path=local_path,
        )
        return "BAAI/bge-small-zh-v1.5"

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

        if self._backend == "fastembed":
            return self._embed_fastembed(texts, batch_size=batch_size)
        return self._embed_sentence_transformers(texts, batch_size=batch_size)

    def _embed_sentence_transformers(
        self,
        texts: list[str],
        *,
        batch_size: int = 32,
    ) -> list[list[float]]:
        """sentence-transformers 后端编码。"""
        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings = self._model.encode(
                batch,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            if isinstance(embeddings, np.ndarray):
                vectors.extend(embeddings.tolist())
            else:
                vectors.extend(list(embeddings))
        return vectors

    def _embed_fastembed(
        self,
        texts: list[str],
        *,
        batch_size: int = 256,
    ) -> list[list[float]]:
        """fastembed 后端编码。

        fastembed 返回 generator of numpy arrays，需要转换为 list[list[float]]。
        """
        embeddings_iter = self._model.embed(texts, batch_size=batch_size)
        vectors: list[list[float]] = []
        for vec in embeddings_iter:
            if isinstance(vec, np.ndarray):
                vectors.append(vec.tolist())
            else:
                vectors.append(list(vec))
        return vectors

    def embed_single(self, text: str) -> list[float]:
        """编码单个文本。"""
        return self.embed([text])[0]

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（主要用于测试）。"""
        if cls._instance is not None and cls._instance._model is not None:
            cls._instance._model = None
        cls._instance = None


def get_embedding_model(
    model_name: str = "bge-m3",
    device: str = "cpu",
) -> EmbeddingModel:
    """获取 Embedding 模型实例的便捷函数。"""
    return EmbeddingModel.get_instance(model_name=model_name, device=device)
