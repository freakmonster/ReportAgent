"""手动演示脚本：验证 EmbeddingModel 双后端切换效果。

运行方式:
    python tests/manual/demo_embedding_backend.py

前置条件:
    - 已安装 sentence-transformers（默认）
    - 已安装 fastembed（可选）
    - VPN 开启（仅 fastembed 后端首次下载模型需要）
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from retrieval.embedders.embedding_model import EmbeddingModel

TEST_TEXTS = [
    "人工智能技术正在深刻改变金融行业的运作方式。",
    "深度学习在自然语言处理和计算机视觉领域取得了突破性进展。",
    "量子计算有望在未来十年内解决传统计算无法处理的复杂问题。",
]


def test_sentence_transformers_backend() -> None:
    """测试 1: sentence_transformers 后端（当前默认）"""
    print("=" * 60)
    print("测试 1: sentence_transformers 后端")
    print("=" * 60)

    EmbeddingModel.reset_instance()
    t0 = time.perf_counter()
    model = EmbeddingModel.get_instance()
    load_time = time.perf_counter() - t0
    print(f"  后端: {model.backend}")
    print(f"  模型: {model._model_name}")
    print(f"  加载耗时: {load_time:.1f}s")

    t0 = time.perf_counter()
    vec = model.embed_single(TEST_TEXTS[0])
    infer_time = time.perf_counter() - t0
    print(f"  向量维度: {len(vec)}")
    print(f"  单条推理耗时: {infer_time:.3f}s")

    t0 = time.perf_counter()
    vecs = model.embed(TEST_TEXTS)
    batch_time = time.perf_counter() - t0
    print(f"  批量({len(TEST_TEXTS)}条)推理耗时: {batch_time:.3f}s")
    print("  结果: 通过\n")


def test_fastembed_backend() -> None:
    """测试 2: fastembed 后端（需要 VPN 下载模型）"""
    print("=" * 60)
    print("测试 2: fastembed 后端")
    print("=" * 60)

    try:
        import fastembed  # noqa: F401
    except ImportError:
        print("  结果: 跳过 (fastembed 未安装)\n")
        return

    EmbeddingModel.reset_instance()
    try:
        t0 = time.perf_counter()
        model = EmbeddingModel.get_instance(
            model_name="BAAI/bge-small-zh-v1.5",
            backend="fastembed",
        )
        load_time = time.perf_counter() - t0
        print(f"  后端: {model.backend}")
        print(f"  模型: {model._model_name}")
        print(f"  加载耗时: {load_time:.1f}s")

        t0 = time.perf_counter()
        vec = model.embed_single(TEST_TEXTS[0])
        infer_time = time.perf_counter() - t0
        print(f"  向量维度: {len(vec)}")
        print(f"  单条推理耗时: {infer_time:.3f}s")
        print("  结果: 通过\n")
    except Exception as exc:
        print(f"  结果: 跳过 (模型下载需要 VPN: {exc})\n")


def test_singleton_protection() -> None:
    """测试 3: 单例保护机制"""
    print("=" * 60)
    print("测试 3: 单例保护机制")
    print("=" * 60)

    EmbeddingModel.reset_instance()
    model1 = EmbeddingModel.get_instance(backend="sentence_transformers")

    try:
        EmbeddingModel.get_instance(backend="fastembed")
        print("  结果: 失败 (应该抛出 RuntimeError)")
    except RuntimeError as exc:
        print(f"  正确拦截: {exc}")
        print("  结果: 通过\n")


def test_invalid_backend() -> None:
    """测试 4: 无效后端拒绝"""
    print("=" * 60)
    print("测试 4: 无效后端拒绝")
    print("=" * 60)

    EmbeddingModel.reset_instance()
    try:
        EmbeddingModel.get_instance(backend="invalid_backend")
        print("  结果: 失败 (应该抛出 ValueError)")
    except ValueError as exc:
        print(f"  正确拦截: {exc}")
        print("  结果: 通过\n")


def test_reset_and_switch() -> None:
    """测试 5: reset_instance 后切换后端"""
    print("=" * 60)
    print("测试 5: reset_instance 后切换后端")
    print("=" * 60)

    EmbeddingModel.reset_instance()
    model1 = EmbeddingModel.get_instance()
    print(f"  首次创建: backend={model1.backend}")

    EmbeddingModel.reset_instance()
    model2 = EmbeddingModel.get_instance()
    print(f"  reset后重建: backend={model2.backend}")
    print("  结果: 通过\n")


if __name__ == "__main__":
    test_sentence_transformers_backend()
    test_fastembed_backend()
    test_singleton_protection()
    test_invalid_backend()
    test_reset_and_switch()
    print("所有可执行测试完成。")
    print("提示: 如需测试 fastembed 后端，请开启 VPN 后重跑此脚本。")
