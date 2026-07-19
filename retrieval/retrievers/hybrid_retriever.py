"""混合检索器 —— BM25 + 语义搜索 + RRF 融合 + 重排序。
重排序未真正实现 _cross_encode_rerank 只按语义分数简单排序，bge-m3 不支持 cross-encode，需要换 bge-reranker-v2 等专用模型
在 BM25 修复上线后观察召回质量，再决定是否需要重排序。"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from infrastructure.observability.logger import get_logger
from retrieval.embedders.embedding_model import EmbeddingModel
from retrieval.retrievers.rerankers.base import BaseReranker
from retrieval.vectorstores.qdrant_store import QdrantStore

logger = get_logger(__name__)


# ── BM25 实现 ────────────────────────────────────────────────────

class BM25Scorer:
    """轻量 BM25 评分器（用于与语义搜索融合）。"""

    k1: float
    b: float
    _doc_count: int
    _avgdl: float
    _idf: dict[str, float]
    _doc_lengths: list[int]
    _term_freqs: list[dict[str, int]]

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._doc_count = 0
        self._avgdl = 0.0
        self._idf = {}
        self._doc_lengths = []
        self._term_freqs = []

    def fit(self, documents: list[str]) -> None:
        """用文档集合训练 BM25 参数。"""
        self._doc_count = len(documents)
        if self._doc_count == 0:
            self._avgdl = 0.0
            self._doc_lengths = []
            self._term_freqs = []
            return

        self._term_freqs = []
        df: dict[str, int] = defaultdict(int)

        for doc in documents:
            tokens = BM25Scorer._tokenize(doc)
            self._doc_lengths.append(len(tokens))
            term_freq: dict[str, int] = defaultdict(int)
            for token in tokens:
                term_freq[token] += 1
            self._term_freqs.append(term_freq)
            for token in set(tokens):
                df[token] += 1

        self._avgdl = sum(self._doc_lengths) / self._doc_count
        self._compute_idf(df)

    def _compute_idf(self, df: dict[str, int]) -> None:
        """计算 IDF 值。"""
        for term, freq in df.items():
            self._idf[term] = math.log(
                (self._doc_count - freq + 0.5) / (freq + 0.5) + 1.0
            )

    def score(self, query: str, doc_index: int) -> float:
        """对单个文档评分。"""
        if doc_index < 0 or doc_index >= self._doc_count:
            return 0.0

        query_tokens = BM25Scorer._tokenize(query)
        term_freq = self._term_freqs[doc_index]
        doc_len = self._doc_lengths[doc_index]

        score = 0.0
        for token in query_tokens:
            tf = term_freq.get(token, 0)
            if tf == 0:
                continue
            idf = self._idf.get(token, 0.0)
            numerator = tf * (self.k1 + 1.0)
            denominator = tf + self.k1 * (1.0 - self.b + self.b * doc_len / self._avgdl)
            score += idf * numerator / denominator
        return score

    def score_all(self, query: str, doc_indices: list[int] | None = None) -> list[tuple[int, float]]:
        """对多个文档评分，返回 [(doc_index, score), ...] 按分数降序。"""
        if doc_indices is None:
            doc_indices = list(range(self._doc_count))
        scores = [(idx, self.score(query, idx)) for idx in doc_indices]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """中英文混合分词。

        中文使用 jieba 搜索引擎模式（cut_for_search），拆分粒度更细，利于检索召回。
        英文使用 \\w+ 正则分词，保持零开销。
        """
        import re
        # 检测是否含中文
        if any('\u4e00' <= c <= '\u9fff' for c in text):
            from jieba import cut_for_search
            tokens = cut_for_search(text)
            # 过滤单字符和纯标点 token，并转小写
            return [t.lower() for t in tokens if len(t.strip()) > 1 and re.search(r'\w', t)]
        # 英文路径：原有逻辑
        tokens = re.findall(r"\w+", text.lower())
        return [t for t in tokens if len(t) > 1]


# ── RRF 融合 ────────────────────────────────────────────────────

def rrf_fusion(
    ranked_lists: list[list[tuple[int, float]]],
    k: int = 60,
) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion (RRF) 融合多路排序结果。

    Args:
        ranked_lists: 多路排序结果，每路为 [(doc_index, score), ...]（从高到低）。
        k: RRF 平滑参数（默认 60，来自经典文献）。

    Returns:
        融合后的排序结果 [(doc_index, rrf_score), ...] 降序。
    """
    rrf_scores: dict[int, float] = defaultdict(float)

    for ranked in ranked_lists:
        for rank, (doc_idx, _) in enumerate(ranked):
            rrf_scores[doc_idx] += 1.0 / (k + rank + 1)

    sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_results


# ── 混合检索器 ──────────────────────────────────────────────────

class HybridRetriever:
    """混合检索器：BM25 + 语义搜索 + RRF 融合 + 可选重排序。"""

    def __init__(
        self,
        qdrant_store: QdrantStore,
        embedder: EmbeddingModel | None = None,
        collection: str = "documents",
        bm25_k1: float = 1.5,
        bm25_b: float = 0.75,
        rrf_k: int = 60,
        reranker: BaseReranker | None = None,
    ) -> None:
        self.qdrant = qdrant_store
        self.embedder = embedder or EmbeddingModel.get_instance()
        self.collection = collection
        self.bm25 = BM25Scorer(k1=bm25_k1, b=bm25_b)
        self.rrf_k = rrf_k
        self.reranker = reranker
        self._documents: list[str] = []
        self._doc_ids: list[str] = []
        self._id_to_idx: dict[str, int] = {}  # cached id→index mapping (H2)
        self._initialized: bool = False
        self._pending_since_refit: int = 0  # docs added since last BM25 refit (H1)

    async def index(self, texts: list[str], metas: list[dict[str, Any]] | None = None) -> list[str]:
        """将文档批量索引入队（BM25 索引 + Qdrant 向量存储）。

        Args:
            texts: 文档文本列表。
            metas: 元数据列表。

        Returns:
            插入的文档 ID 列表。
        """
        # 向量存储
        ids = await self.qdrant.upsert(
            collection=self.collection,
            texts=texts,
            metas=metas,
            embedder=self.embedder,
        )

        # BM25 索引
        self._documents.extend(texts)
        self._doc_ids.extend(ids)
        self._pending_since_refit += len(texts)

        # 缓存 id→index 映射
        for idx, did in enumerate(self._doc_ids):
            self._id_to_idx[did] = idx

        # 批次阈值达到时才重建 BM25
        _BM25_REFIT_BATCH = 50
        if self._pending_since_refit >= _BM25_REFIT_BATCH:
            self._refit_bm25()
            self._pending_since_refit = 0

        self._initialized = True
        logger.info("Hybrid index updated", count=len(ids), total=len(self._documents))
        return ids

    def _refit_bm25(self) -> None:
        """重新训练 BM25 模型。"""
        if self._documents:
            self.bm25.fit(self._documents)

    def force_refit(self) -> None:
        """显式强制重建 BM25 索引（例如批量导入完成后调用）。"""
        self._refit_bm25()
        self._pending_since_refit = 0

    async def _ensure_loaded(self) -> None:
        """从 Qdrant 加载已有文档到本地 BM25 索引（幂等）。"""
        if self._initialized:
            return
        client = await self.qdrant._get_client()
        col_name = self.qdrant._collection_name(self.collection)
        offset = None
        while True:
            result, offset = await client.scroll(
                collection_name=col_name,
                limit=500,
                with_payload=True,
                with_vectors=False,
                offset=offset,
            )
            if not result:
                break
            for pt in result:
                text = (pt.payload or {}).get("text", "")
                if text:
                    self._documents.append(text)
                    self._doc_ids.append(pt.id)
            if offset is None:
                break
        for idx, did in enumerate(self._doc_ids):
            self._id_to_idx[did] = idx
        self._refit_bm25()
        self._initialized = True
        logger.info("HybridRetriever loaded from Qdrant", docs=len(self._documents))

    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        semantic_weight: float = 0.7,
        bm25_weight: float = 0.3,
        rerank: bool = False,
        rerank_top_n: int = 20,
    ) -> list[dict[str, Any]]:
        """混合检索。

        Args:
            query: 查询文本。
            top_k: 返回结果数。
            semantic_weight: 语义搜索权重（RRF 中通过候选数控制）。
            bm25_weight: BM25 权重。
            rerank: 是否启用交叉编码器重排序。
            rerank_top_n: 重排序候选数量。

        Returns:
            搜索结果列表。
        """
        # 自动 refit 延迟的 BM25（H1）
        if self._pending_since_refit > 0:
            self._refit_bm25()
            self._pending_since_refit = 0

        # 从 Qdrant 加载已有文档（首次搜索时懒加载）
        await self._ensure_loaded()

        # 语义搜索
        semantic_limit = max(top_k * 3, 30)
        semantic_results = await self.qdrant.search(
            collection=self.collection,
            query=query,
            limit=semantic_limit,
            embedder=self.embedder,
        )

        # 构建语义搜索的 ranked list 用于 RRF
        semantic_indexed: list[tuple[int, float]] = []
        sem_map: dict[int, float] = {}

        for rank, result in enumerate(semantic_results):
            idx = self._id_to_idx.get(result["id"])
            if idx is not None:
                sem_map[idx] = result["score"]
                semantic_indexed.append((idx, result["score"]))

        # BM25 搜索
        all_bm25 = self.bm25.score_all(query)
        bm25_limit = max(top_k * 3, 30)
        bm25_indexed: list[tuple[int, float]] = []

        for idx, score in all_bm25[:bm25_limit]:
            if score > 0:
                bm25_indexed.append((idx, score))

        # RRF 融合
        fused = rrf_fusion([semantic_indexed, bm25_indexed], k=self.rrf_k)

        # 取 top_k 或 rerank_top_n
        candidate_count = rerank_top_n if rerank else top_k
        top_candidates = fused[:candidate_count]

        results: list[dict[str, Any]] = []
        for doc_idx, rrf_score in top_candidates:
            doc_id = self._doc_ids[doc_idx]
            text = self._documents[doc_idx]
            sem_score = sem_map.get(doc_idx, 0.0)
            results.append({
                "id": doc_id,
                "text": text,
                "score": rrf_score,
                "semantic_score": sem_score,
                "bm25_score": self.bm25.score(query, doc_idx),
            })

        if rerank and self.reranker is not None and len(results) > top_k:
            results = await self.reranker.rerank(query, results, top_k)

        return results[:top_k]

    async def search_batch(
        self,
        queries: list[str],
        *,
        top_k: int = 10,
        **kwargs: Any,
    ) -> list[list[dict[str, Any]]]:
        """批量混合检索。"""
        results: list[list[dict[str, Any]]] = []
        for query in queries:
            results.append(await self.search(query, top_k=top_k, **kwargs))
        return results

    @property
    def document_count(self) -> int:
        """索引中的文档数量。"""
        return len(self._documents)
