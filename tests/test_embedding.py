"""Tests for embedding providers."""

import pytest

from dynatrust_rag.embedding import (
    LocalEmbeddingProvider,
    EMBEDDING_DIM,
    get_default_embedding_provider,
    reset_default_provider,
)


@pytest.fixture(autouse=True)
def reset_provider():
    """Reset singleton between tests."""
    reset_default_provider()
    yield
    reset_default_provider()


class TestLocalEmbeddingProvider:
    @pytest.mark.asyncio
    async def test_embed_text_dimension(self):
        provider = LocalEmbeddingProvider()
        embedding = await provider.embed_text("Hello world")
        assert len(embedding) == EMBEDDING_DIM

    @pytest.mark.asyncio
    async def test_embed_text_deterministic(self):
        provider = LocalEmbeddingProvider()
        e1 = await provider.embed_text("Hello world")
        e2 = await provider.embed_text("Hello world")
        assert e1 == e2

    @pytest.mark.asyncio
    async def test_embed_text_different_inputs(self):
        provider = LocalEmbeddingProvider()
        e1 = await provider.embed_text("Hello")
        e2 = await provider.embed_text("World")
        assert e1 != e2

    @pytest.mark.asyncio
    async def test_embed_batch(self):
        provider = LocalEmbeddingProvider()
        texts = ["First", "Second", "Third"]
        embeddings = await provider.embed_batch(texts)
        assert len(embeddings) == 3
        assert all(len(e) == EMBEDDING_DIM for e in embeddings)

    @pytest.mark.asyncio
    async def test_embed_batch_empty(self):
        provider = LocalEmbeddingProvider()
        embeddings = await provider.embed_batch([])
        assert embeddings == []

    @pytest.mark.asyncio
    async def test_values_in_range(self):
        provider = LocalEmbeddingProvider()
        embedding = await provider.embed_text("test")
        assert all(-1.0 <= v <= 1.0 for v in embedding)


class TestDefaultProvider:
    @pytest.mark.asyncio
    async def test_default_provider_is_local(self):
        """With DYNATRUST_EMBEDDING_PROVIDER=local, should get LocalEmbeddingProvider."""
        provider = await get_default_embedding_provider()
        assert isinstance(provider, LocalEmbeddingProvider)
