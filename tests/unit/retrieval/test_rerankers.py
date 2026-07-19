"""Unit tests for rerankers — NoOp, CrossEncoder, factory, and strategy pattern."""

import pytest

from retrieval.retrievers.rerankers import get_reranker
from retrieval.retrievers.rerankers.base import BaseReranker
from retrieval.retrievers.rerankers.cross_encoder_reranker import CrossEncoderReranker
from retrieval.retrievers.rerankers.noop_reranker import NoOpReranker


class TestNoOpReranker:
    async def test_passthrough(self):
        reranker = NoOpReranker()
        candidates = [
            {"id": "3", "text": "doc3", "score": 0.5},
            {"id": "1", "text": "doc1", "score": 0.9},
            {"id": "2", "text": "doc2", "score": 0.7},
        ]
        result = await reranker.rerank("query", candidates, top_k=2)
        assert len(result) == 2
        assert result == candidates[:2]

    async def test_top_k_exceeds_candidates(self):
        reranker = NoOpReranker()
        candidates = [{"id": "1", "text": "doc", "score": 0.9}]
        result = await reranker.rerank("q", candidates, top_k=5)
        assert len(result) == 1

    async def test_empty_candidates(self):
        reranker = NoOpReranker()
        result = await reranker.rerank("q", [], top_k=3)
        assert result == []


class TestCrossEncoderReranker:
    async def test_empty_candidates_no_load(self):
        """Empty candidate list skips model loading entirely."""
        reranker = CrossEncoderReranker()
        assert reranker._model is None
        result = await reranker.rerank("q", [], top_k=3)
        assert result == []
        assert reranker._model is None  # never loaded

    def test_subclass_of_base(self):
        assert issubclass(NoOpReranker, BaseReranker)
        assert issubclass(CrossEncoderReranker, BaseReranker)

    def test_model_name_default(self):
        reranker = CrossEncoderReranker()
        assert "bge-reranker" in reranker._model_name


class TestGetReranker:
    def test_returns_noop_by_default(self, mocker):
        """get_reranker() returns NoOpReranker when settings.reranker_enabled=False."""
        mocker.patch("retrieval.retrievers.rerankers.settings.reranker_enabled", False)
        reranker = get_reranker()
        assert isinstance(reranker, NoOpReranker)

    def test_returns_cross_encoder_when_enabled(self, mocker):
        """get_reranker() returns CrossEncoderReranker when enabled."""
        mocker.patch("retrieval.retrievers.rerankers.settings.reranker_enabled", True)
        mocker.patch(
            "retrieval.retrievers.rerankers.settings.reranker_model",
            "BAAI/bge-reranker-v2-m3",
        )
        reranker = get_reranker()
        assert isinstance(reranker, CrossEncoderReranker)
        assert reranker._model is None  # not loaded yet
