"""
Embedding 模型对比评测：GTE-base vs bge-m3
指标：维度、显存、推理延迟、语义相关度、BM25 互补性、RRF 排序质量
"""
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field

# 禁用 HF 在线请求
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# ── 测试数据 ──
CORPUS = [
    "LangGraph是一个用于构建有状态多智能体应用的框架，支持检查点、中断和人工审查。",
    "多智能体系统通过分工协作解决复杂问题，包括分析、搜索、撰写和审查等角色。",
    "Qdrant是一个高性能向量数据库，支持混合检索和BM25全文搜索。",
    "RAG检索增强生成技术结合外部知识库和LLM，减少幻觉，提升事实准确性。",
    "PostgreSQL是一种开源关系型数据库，支持ACID事务和JSONB数据类型。",
    "Redis是一个内存数据结构存储，用作数据库、缓存和消息代理。",
    "Docker容器技术实现应用打包和隔离部署，支持微服务架构。",
    "Kubernetes是容器编排平台，自动化部署、扩展和管理容器化应用。",
]

QUERIES = [
    ("精确匹配", "什么是LangGraph？", 0),
    ("语义相关", "数据库技术有哪些？", [4, 5]),
    ("组合概念", "容器编排和微服务", [6, 7]),
    ("跨领域", "AI如何与数据库结合？", [0, 3, 4]),
]

@dataclass
class ModelMetrics:
    name: str
    dimension: int = 0
    load_time: float = 0.0
    encode_time_1: float = 0.0
    encode_time_batch: float = 0.0
    semantic_scores: list = field(default_factory=list)
    mrrs: list = field(default_factory=list)
    top1_hits: int = 0
    total_queries: int = 0

async def test_model(model_path: str, name: str) -> ModelMetrics:
    mm = ModelMetrics(name=name)

    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"Path: {model_path}")

    # ── 0. 重置 EmbeddingModel 单例 ──
    from retrieval.embedders.embedding_model import EmbeddingModel
    EmbeddingModel.reset_instance()

    import httpx
    async with httpx.AsyncClient() as c:
        await c.delete("http://localhost:6333/collections/research_agent_bench")

    # ── 1. 加载时间 ──
    t0 = time.time()
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_path)
    mm.dimension = model.get_sentence_embedding_dimension()
    mm.load_time = time.time() - t0
    print(f"  维度: {mm.dimension} | 加载耗时: {mm.load_time:.2f}s")

    # ── 2. 推理延迟 ──
    single_text = CORPUS[0]
    t0 = time.time()
    for _ in range(10):
        _ = model.encode(single_text)
    mm.encode_time_1 = (time.time() - t0) / 10 * 1000  # ms
    print(f"  单条推理: {mm.encode_time_1:.1f}ms (avg of 10)")

    t0 = time.time()
    for _ in range(10):
        _ = model.encode(CORPUS)
    mm.encode_time_batch = (time.time() - t0) / 10 * 1000
    print(f"  批量推理 (8条): {mm.encode_time_batch:.1f}ms (avg of 10)")

    # ── 3. 构建索引 + 混合检索评测 ──
    from retrieval.embedders.embedding_model import EmbeddingModel as EM
    from retrieval.pipelines.build_index import IndexBuilder
    from retrieval.retrievers.hybrid_retriever import HybridRetriever
    from retrieval.vectorstores.qdrant_store import QdrantStore

    store = QdrantStore(embedding_dimension=mm.dimension)
    # Explicitly pass model_path to bypass settings
    embedder = EM.get_instance(model_name=model_path)
    builder = IndexBuilder(qdrant_store=store, base_collection="bench", embedder=embedder)
    await builder.build_from_texts(CORPUS)

    retriever = HybridRetriever(store, embedder, collection="bench")

    print("\n  检索评测:")
    print(f"  {'Query':<16} {'Top-1':<10} {'sem':>8} {'bm25':>8} {'RRF':>8} {'Hit':>6}")
    print(f"  {'-'*16} {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*6}")

    for qtype, query, expected in QUERIES:
        results = await retriever.search(query, top_k=3)
        top1_id = results[0]["id"] if results else "NONE"

        # 找 top-1 对应的语料索引
        hit = False
        if results:
            for i, c in enumerate(CORPUS):
                if c[:30] in results[0].get("text", ""):
                    hit = (i == expected) if isinstance(expected, int) else (i in expected)
                    break

        sem = results[0].get("semantic_score", 0) if results else 0
        bm25 = results[0].get("bm25_score", 0) if results else 0
        rrf = results[0]["score"] if results else 0

        mm.semantic_scores.append(sem)
        if hit:
            mm.top1_hits += 1
        mm.total_queries += 1

        marker = "HIT" if hit else "MISS"
        print(f"  {qtype:<16} {top1_id[:10]:<10} {sem:>8.4f} {bm25:>8.4f} {rrf:>8.4f} {marker:>6}")

    await store.close()
    return mm


async def main():
    models = [
        ("E:/models/bge-m3", "bge-m3 (1024d)"),
        ("E:/models/iic--nlp_gte_sentence-embedding_chinese-base/snapshots/master", "GTE-base (768d)"),
    ]

    results = []
    for path, name in models:
        if not os.path.isdir(path):
            print(f"SKIP: {path} not found")
            continue
        r = await test_model(path, name)
        results.append(r)

    # ── 汇总 ──
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'Metric':<22}", end="")
    for r in results:
        print(f"  {r.name:<24}", end="")
    print()
    print("-" * 70)

    rows = [
        ("Dimension", lambda r: str(r.dimension)),
        ("Load time (s)", lambda r: f"{r.load_time:.2f}"),
        ("Encode 1x (ms)", lambda r: f"{r.encode_time_1:.1f}"),
        ("Encode 8x batch (ms)", lambda r: f"{r.encode_time_batch:.1f}"),
        ("Top-1 Hits", lambda r: f"{r.top1_hits}/{r.total_queries}"),
        ("Avg Semantic Score", lambda r: f"{sum(r.semantic_scores)/len(r.semantic_scores):.4f}" if r.semantic_scores else "N/A"),
    ]
    for label, fn in rows:
        print(f"  {label:<22}", end="")
        for r in results:
            print(f"  {fn(r):<24}", end="")
        print()

    # ── 结论 ──
    if len(results) >= 2:
        r1, r2 = results[0], results[1]
        faster = r1.name if r1.encode_time_1 < r2.encode_time_1 else r2.name
        better_retrieval = r1.name if r1.top1_hits >= r2.top1_hits else r2.name
        print(f"\n  Faster inference: {faster}")
        print(f"  Better retrieval: {better_retrieval}")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
