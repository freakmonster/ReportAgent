"""Unit tests for qdrant_store — collection CRUD, upsert, search, double buffer."""

import pytest

from retrieval.vectorstores.qdrant_store import QdrantStore


class TestQdrantStore:
    def setup_method(self):
        self.store = QdrantStore(
            host="localhost",
            port=6333,
            collection_prefix="test",
            embedding_dimension=1024,
        )

    async def test_create_collection(self, mocker):
        mock_client = mocker.AsyncMock()
        mock_client.create_collection = mocker.AsyncMock()
        mock_client.get_collections = mocker.AsyncMock(
            return_value=mocker.MagicMock(collections=[])
        )
        mocker.patch.object(self.store, "_get_client", return_value=mock_client)

        result = await self.store.create_collection("docs")
        assert result is True
        mock_client.create_collection.assert_called_once()

    async def test_collection_exists(self, mocker):
        mock_client = mocker.AsyncMock()
        fake_col = mocker.MagicMock()
        fake_col.name = "test_docs"
        mock_client.get_collections = mocker.AsyncMock(
            return_value=mocker.MagicMock(collections=[fake_col])
        )
        mocker.patch.object(self.store, "_get_client", return_value=mock_client)

        exists = await self.store.collection_exists("docs")
        assert exists is True

    async def test_upsert(self, mocker):
        mock_client = mocker.AsyncMock()
        mock_client.upsert = mocker.AsyncMock()
        mocker.patch.object(self.store, "_get_client", return_value=mock_client)

        # Mock embedder to avoid real model loading
        mock_embedder = mocker.MagicMock()
        mock_embedder.embed.return_value = [[0.1] * 1024, [0.2] * 1024]

        await self.store.create_collection("docs")

        ids = await self.store.upsert(
            collection="docs",
            texts=["doc1", "doc2"],
            embedder=mock_embedder,
        )
        assert len(ids) == 2
        mock_client.upsert.assert_called_once()

    async def test_search(self, mocker):
        mock_client = mocker.AsyncMock()
        fake_hit = mocker.MagicMock(
            id="id1",
            payload={"text": "result text"},
            score=0.95,
        )
        mock_client.query_points = mocker.AsyncMock(
            return_value=mocker.MagicMock(points=[fake_hit])
        )
        mocker.patch.object(self.store, "_get_client", return_value=mock_client)

        mock_embedder = mocker.MagicMock()
        mock_embedder.embed_single.return_value = [0.1] * 1024

        results = await self.store.search(
            collection="docs",
            query="test query",
            embedder=mock_embedder,
        )
        assert len(results) == 1
        assert results[0]["id"] == "id1"
        assert results[0]["score"] == 0.95

    async def test_search_batch(self, mocker):
        mock_client = mocker.AsyncMock()
        single_result = [
            mocker.MagicMock(
                id="id1",
                payload={"text": "result"},
                score=0.9,
            ),
        ]
        mock_client.search_batch = mocker.AsyncMock(return_value=[single_result, single_result])
        mocker.patch.object(self.store, "_get_client", return_value=mock_client)

        mock_embedder = mocker.MagicMock()
        mock_embedder.embed.return_value = [[0.1] * 1024, [0.2] * 1024]

        results = await self.store.search_batch(
            collection="docs",
            queries=["q1", "q2"],
            embedder=mock_embedder,
        )
        assert len(results) == 2
        assert len(results[0]) == 1
