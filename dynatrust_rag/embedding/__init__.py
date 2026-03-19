"""
DynaTrust-RAG Embedding Module

Provides a unified interface for generating text embeddings using
various backends (OpenAI, HuggingFace, local models).
"""

from .provider import (
    EmbeddingProvider,
    OpenAIEmbeddingProvider,
    LocalEmbeddingProvider,
    get_default_embedding_provider,
    reset_default_provider,
    EMBEDDING_DIM,
)

__all__ = [
    "EmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "LocalEmbeddingProvider",
    "get_default_embedding_provider",
    "reset_default_provider",
    "EMBEDDING_DIM",
]
