"""
DynaTrust-RAG Retrieval Module

Hybrid retrieval system combining:
- Semantic search via pgvector
- Spatial search via PostGIS
- Structured SQL queries

The retrieval router classifies queries and orchestrates
the appropriate retrieval strategies.
"""

from .base import BaseRetriever, RetrievalResult, DocumentChunk, StructuredRow, SpatialRow
from .semantic import SemanticRetriever
from .spatial import SpatialRetriever
from .structured import StructuredRetriever
from .router import HybridRetrievalRouter, hybrid_retrieve

__all__ = [
    "BaseRetriever",
    "RetrievalResult",
    "DocumentChunk",
    "StructuredRow",
    "SpatialRow",
    "SemanticRetriever",
    "SpatialRetriever",
    "StructuredRetriever",
    "HybridRetrievalRouter",
    "hybrid_retrieve",
]
