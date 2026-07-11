"""Unit tests for embedding_model — singleton, lazy load, batch encode.

NOTE: sentence_transformers imports torch which crashes with WinError 1114 on
this machine's virtual env.  Instead of patching the upstream package (which
triggers the broken import), we directly manipulate the private `_model`
attribute on EmbeddingModel to simulate a loaded state.
"""

import numpy as np
import pytest
from retrieval.embedders.embedding_model import EmbeddingModel


class TestEmbeddingModel:
    def setup_method(self):
        EmbeddingModel.reset_instance()

    def test_singleton(self):
        m1 = EmbeddingModel.get_instance()
        m2 = EmbeddingModel.get_instance()
        assert m1 is m2

    def test_lazy_load_skipped_when_model_is_set(self, mocker):
        """If _model is already set, _ensure_loaded is a no-op."""
        instance = EmbeddingModel.get_instance()

        # Inject a fake model — should prevent real SentenceTransformer import
        fake = mocker.MagicMock()
        fake.get_sentence_embedding_dimension.return_value = 1024
        fake.encode.return_value = np.zeros((1, 1024))
        instance._model = fake

        # Must NOT try to import sentence_transformers
        instance._ensure_loaded()
        # No exception → lazy-load guard works

    def test_dimension_1024(self, mocker):
        instance = EmbeddingModel.get_instance()
        fake = mocker.MagicMock()
        fake.get_sentence_embedding_dimension.return_value = 1024
        fake.encode.return_value = np.zeros((1, 1024))
        instance._model = fake
        assert instance.dimension == 1024

    def test_embed_batch(self, mocker):
        instance = EmbeddingModel.get_instance()
        fake = mocker.MagicMock()
        fake.get_sentence_embedding_dimension.return_value = 1024
        fake.encode.return_value = np.ones((3, 1024))
        instance._model = fake

        vectors = instance.embed(["a", "b", "c"])
        assert len(vectors) == 3
        assert len(vectors[0]) == 1024

    def test_embed_single(self, mocker):
        instance = EmbeddingModel.get_instance()
        fake = mocker.MagicMock()
        fake.get_sentence_embedding_dimension.return_value = 1024
        fake.encode.return_value = np.ones((1, 1024))
        instance._model = fake

        vector = instance.embed_single("hello")
        assert len(vector) == 1024

    def test_embed_empty_list_no_load(self):
        """Method returns [] BEFORE model is loaded — pure fast-path."""
        instance = EmbeddingModel.get_instance()
        assert instance._model is None
        vectors = instance.embed([])
        assert vectors == []
        assert instance._model is None  # still not loaded

    def test_singleton_param_conflict_raises(self):
        """Second get_instance() with different params raises RuntimeError."""
        EmbeddingModel.reset_instance()
        EmbeddingModel.get_instance(model_name="bge-m3", device="cpu")

        with pytest.raises(RuntimeError, match="already initialized"):
            EmbeddingModel.get_instance(model_name="other-model", device="cpu")

        with pytest.raises(RuntimeError, match="already initialized"):
            EmbeddingModel.get_instance(model_name="bge-m3", device="cuda")
