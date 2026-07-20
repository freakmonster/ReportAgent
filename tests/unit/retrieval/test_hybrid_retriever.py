"""Unit tests for hybrid_retriever — BM25 + semantic + RRF fusion + rerank."""

import pytest

from retrieval.retrievers.hybrid_retriever import (
    BM25Scorer,
    HybridRetriever,
    rrf_fusion,
)


class TestBM25Scorer:
    def test_simple_scoring(self):
        docs = ["the quick brown fox", "the lazy dog", "quick brown fox jumps"]
        bm25 = BM25Scorer()
        bm25.fit(docs)
        scores = bm25.score_all("quick fox")
        assert len(scores) == 3
        # "the quick brown fox" and "quick brown fox jumps" should score higher
        assert scores[0][1] > scores[2][1]  # first or third should beat "the lazy dog"

    def test_empty_fit(self):
        bm25 = BM25Scorer()
        bm25.fit([])
        scores = bm25.score_all("test")
        assert scores == []

    def test_score_invalid_index(self):
        bm25 = BM25Scorer()
        bm25.fit(["doc1", "doc2"])
        assert bm25.score("query", -1) == 0.0
        assert bm25.score("query", 100) == 0.0

    def test_chinese_tokenization(self):
        """jieba cut_for_search generates search-optimized Chinese tokens."""
        tokens = BM25Scorer._tokenize("量子计算机技术突破")
        # cut_for_search: 量子 / 计算 / 计算机 / 技术 / 突破
        assert "量子" in tokens
        assert "计算机" in tokens
        assert "突破" in tokens
        assert len(tokens) >= 4  # at minimum: 量子 计算 计算机 突破

    def test_chinese_bm25_scoring(self):
        """BM25 scores Chinese docs correctly with jieba tokenization."""
        docs = [
            "量子计算机是一种利用量子力学原理进行计算的新型计算机",
            "今天天气很好适合出去散步",
            "量子计算与人工智能的结合将改变世界",
        ]
        bm25 = BM25Scorer()
        bm25.fit(docs)
        scores = bm25.score_all("量子计算机")
        assert len(scores) == 3
        # First doc (about quantum computers) should rank highest
        assert scores[0][0] == 0
        assert scores[0][1] > 0
        # Second doc (about weather) should have lowest score for quantum query
        assert scores[2][1] >= 0  # may be non-zero due to partial token overlap

    def test_mixed_chinese_english_tokenization(self):
        """Mixed Chinese-English text tokenizes both correctly."""
        tokens = BM25Scorer._tokenize("使用 Python 开发量子 AI 系统")
        assert "python" in tokens
        assert "量子" in tokens
        assert "ai" in tokens or "系统" in tokens


class TestRRFFusion:
    def test_fuses_two_lists(self):
        list_a = [(0, 0.9), (1, 0.7), (2, 0.5)]
        list_b = [(1, 0.8), (2, 0.6), (0, 0.3)]
        fused = rrf_fusion([list_a, list_b], k=60)
        assert len(fused) == 3
        # 1 appears at rank 1 (list_b[0]) and rank 1 (list_a[1])
        assert fused[0][0] == 1


class TestHybridRetriever:
    async def test_index_and_search(self, mocker):
        store = mocker.AsyncMock()
        mock_embedder = mocker.MagicMock()
        mock_embedder.embed_single.return_value = [0.1] * 1024

        fake_result = mocker.MagicMock(
            id="id1",
            payload={"text": "result"},
            score=0.95,
        )
        store.search = mocker.AsyncMock(return_value=[fake_result])
        store.upsert = mocker.AsyncMock(return_value=["id1", "id2"])

        retriever = HybridRetriever(
            qdrant_store=store,
            embedder=mock_embedder,
            collection="test",
        )

        ids = await retriever.index(["doc one", "doc two"])
        assert len(ids) == 2

        results = await retriever.search("doc")
        assert len(results) > 0

    async def test_search_empty_index(self, mocker):
        store = mocker.AsyncMock()
        store.search = mocker.AsyncMock(return_value=[])

        # Mock _get_client + scroll for _ensure_loaded() when no docs exist
        mock_client = mocker.AsyncMock()
        mock_client.scroll = mocker.AsyncMock(return_value=([], None))
        store._get_client = mocker.AsyncMock(return_value=mock_client)
        store._collection_name = mocker.MagicMock(return_value="test_documents")

        mock_embedder = mocker.MagicMock()
        mock_embedder.embed_single.return_value = [0.1] * 1024

        retriever = HybridRetriever(
            qdrant_store=store,
            embedder=mock_embedder,
        )
        results = await retriever.search("anything")
        assert results == []

    async def test_search_with_rerank(self, mocker):
        store = mocker.AsyncMock()
        mock_embedder = mocker.MagicMock()
        mock_embedder.embed_single.return_value = [0.1] * 1024

        fake_results = [
            mocker.MagicMock(id=f"id{i}", payload={"text": f"doc{i}"}, score=0.9 - i * 0.1)
            for i in range(5)
        ]
        store.search = mocker.AsyncMock(return_value=fake_results)
        store.upsert = mocker.AsyncMock(return_value=[f"id{i}" for i in range(5)])

        retriever = HybridRetriever(
            qdrant_store=store,
            embedder=mock_embedder,
        )
        await retriever.index([f"document number {i}" for i in range(5)])

        # Without reranker injected, rerank=True should degrade gracefully
        results = await retriever.search("document", top_k=3, rerank=True)
        assert len(results) <= 3

    async def test_search_batch(self, mocker):
        store = mocker.AsyncMock()
        mock_embedder = mocker.MagicMock()
        mock_embedder.embed_single.return_value = [0.1] * 1024

        store.search = mocker.AsyncMock(return_value=[])
        store.upsert = mocker.AsyncMock(return_value=["id1"])

        retriever = HybridRetriever(
            qdrant_store=store,
            embedder=mock_embedder,
        )
        await retriever.index(["doc"])

        results = await retriever.search_batch(["q1", "q2"], top_k=3)
        assert len(results) == 2
