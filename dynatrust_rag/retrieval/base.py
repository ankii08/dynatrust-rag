"""
DynaTrust-RAG Base Retriever Interfaces

Defines the core data structures and abstract interfaces for all retrieval
strategies in the DynaTrust-RAG system.

Design Principles:
- Clean separation between semantic, spatial, and structured retrieval
- All results carry provenance metadata for attribution tracking
- Each retriever produces its own score in [0, 1] for local ranking
- Type-safe with Pydantic models for serialization

Data Flow:
    QueryRequest → BaseRetriever.retrieve() → RetrievalResult
                                               ├── semantic_chunks
                                               ├── structured_rows
                                               ├── spatial_rows
                                               └── executed_sql (for provenance)
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol, Union, runtime_checkable

from pydantic import BaseModel, Field


# =============================================================================
# Lightweight Result Models
# =============================================================================

class DocumentChunk(BaseModel):
    """
    A single text chunk retrieved via semantic (vector) search.
    
    Attributes:
        id: Database primary key of the chunk
        chunk_id: Logical identifier (format: {doc_id}#chunk_{index})
        text: The actual text content
        score: Similarity score normalized to [0, 1] (higher = more similar)
        source_doc: Identifier of the source document
        section: Optional section/heading within the document
        metadata: Additional metadata (source_type, created_at, etc.)
    """
    id: int = Field(..., description="Database primary key")
    chunk_id: str = Field(..., description="Logical chunk identifier")
    text: str = Field(..., description="Text content of the chunk")
    score: float = Field(..., ge=0.0, le=1.0, description="Similarity score [0,1]")
    source_doc: str = Field(..., description="Source document identifier")
    section: Optional[str] = Field(None, description="Section within document")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        frozen = True


class StructuredRow(BaseModel):
    """
    A row retrieved from a structured SQL query (non-spatial).
    
    Attributes:
        table_name: Name of the source table
        primary_key: Primary key value(s) of the row
        data: Column name → value mapping
        score: Relevance score (1.0 for exact matches, can be lower for fuzzy)
    """
    table_name: str = Field(..., description="Source table name")
    primary_key: Union[int, str, Dict[str, Any]] = Field(..., description="Primary key value")
    data: Dict[str, Any] = Field(default_factory=dict, description="Row data as dict")
    score: float = Field(1.0, ge=0.0, le=1.0, description="Relevance score")

    class Config:
        frozen = True


class SpatialRow(BaseModel):
    """
    A row retrieved from a spatial (PostGIS) query.
    
    Attributes:
        table_name: Name of the source table
        primary_key: Primary key value of the row
        wkt_geometry: Well-Known Text representation of the geometry
        distance_meters: Distance from query point (if applicable)
        data: Column name → value mapping (excluding geometry)
        score: Relevance score based on distance (closer = higher)
    """
    table_name: str = Field(..., description="Source table name")
    primary_key: Union[int, str] = Field(..., description="Primary key value")
    wkt_geometry: Optional[str] = Field(None, description="WKT geometry string")
    distance_meters: Optional[float] = Field(None, description="Distance from query point")
    data: Dict[str, Any] = Field(default_factory=dict, description="Row data as dict")
    score: float = Field(1.0, ge=0.0, le=1.0, description="Relevance score")

    class Config:
        frozen = True


# =============================================================================
# Unified Retrieval Result
# =============================================================================

class RetrievalResult(BaseModel):
    """
    Unified result container from hybrid retrieval.
    
    Aggregates results from semantic, spatial, and structured retrievers,
    plus the SQL queries executed for provenance tracking.
    
    Attributes:
        semantic_chunks: Text chunks from vector search
        structured_rows: Rows from structured SQL queries
        spatial_rows: Rows from spatial (PostGIS) queries
        executed_sql: List of SQL statements executed (for provenance)
        metadata: Additional info (retrievers_used, timings, etc.)
    """
    semantic_chunks: List[DocumentChunk] = Field(
        default_factory=list,
        description="Text chunks from semantic/vector retrieval"
    )
    structured_rows: List[StructuredRow] = Field(
        default_factory=list,
        description="Rows from structured SQL queries"
    )
    spatial_rows: List[SpatialRow] = Field(
        default_factory=list,
        description="Rows from spatial PostGIS queries"
    )
    executed_sql: List[str] = Field(
        default_factory=list,
        description="SQL queries executed (for provenance)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (retrievers_used, timings, etc.)"
    )
    
    @property
    def total_results(self) -> int:
        """Total number of results across all retrievers."""
        return len(self.semantic_chunks) + len(self.structured_rows) + len(self.spatial_rows)
    
    @property
    def is_empty(self) -> bool:
        """Check if no results were retrieved."""
        return self.total_results == 0
    
    def merge(self, other: "RetrievalResult") -> "RetrievalResult":
        """
        Merge another RetrievalResult into a new combined result.
        
        Args:
            other: Another RetrievalResult to merge
            
        Returns:
            New RetrievalResult with combined results
        """
        merged_metadata = {**self.metadata, **other.metadata}
        
        # Combine retrievers_used lists if present
        self_retrievers = self.metadata.get("retrievers_used", [])
        other_retrievers = other.metadata.get("retrievers_used", [])
        if self_retrievers or other_retrievers:
            merged_metadata["retrievers_used"] = list(set(self_retrievers + other_retrievers))
        
        return RetrievalResult(
            semantic_chunks=self.semantic_chunks + other.semantic_chunks,
            structured_rows=self.structured_rows + other.structured_rows,
            spatial_rows=self.spatial_rows + other.spatial_rows,
            executed_sql=self.executed_sql + other.executed_sql,
            metadata=merged_metadata,
        )
    
    def get_chunk_ids(self) -> List[str]:
        """Get all chunk IDs for provenance."""
        return [chunk.chunk_id for chunk in self.semantic_chunks]
    
    def get_row_references(self) -> List[Dict[str, Any]]:
        """Get all row references for provenance."""
        refs = []
        for row in self.structured_rows:
            refs.append({"table": row.table_name, "id": row.primary_key})
        for row in self.spatial_rows:
            refs.append({"table": row.table_name, "id": row.primary_key})
        return refs


# =============================================================================
# Abstract Base Retriever
# =============================================================================

# Forward reference for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..api.schemas import QueryRequest


@runtime_checkable
class RetrieverProtocol(Protocol):
    """Protocol defining the retriever interface for type checking."""
    
    async def retrieve(self, query: "QueryRequest", limit: int = 10) -> RetrievalResult:
        """Execute retrieval and return results."""
        ...
    
    async def health_check(self) -> bool:
        """Check if the retriever is healthy."""
        ...


class BaseRetriever(ABC):
    """
    Abstract base class for all retrieval strategies.
    
    Subclasses implement specific retrieval logic for:
    - SemanticRetriever: pgvector similarity search
    - SpatialRetriever: PostGIS geographic queries  
    - StructuredRetriever: SQL-based attribute filtering
    
    All retrievers:
    - Accept a QueryRequest and return a RetrievalResult
    - Track executed SQL for provenance
    - Normalize scores to [0, 1] range
    """
    
    # Default limits
    DEFAULT_LIMIT = 10
    MAX_LIMIT = 100
    
    def __init__(self, pool=None):
        """
        Initialize the retriever.
        
        Args:
            pool: Optional asyncpg connection pool. If not provided,
                  will use the shared pool from db.connection.
        """
        self._pool = pool
    
    async def get_pool(self):
        """Get the database connection pool."""
        if self._pool is not None:
            return self._pool
        
        from ..db.connection import get_pool
        return await get_pool()
    
    @abstractmethod
    async def retrieve(self, query: "QueryRequest", limit: int = 10) -> RetrievalResult:
        """
        Execute a retrieval operation.
        
        Args:
            query: The QueryRequest containing the question and constraints
            limit: Maximum number of results to return
            
        Returns:
            RetrievalResult with retrieved items and executed SQL
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the retriever's backing store is healthy.
        
        Returns:
            True if healthy and ready to serve queries
        """
        pass
    
    @staticmethod
    def normalize_score(raw_score: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
        """
        Normalize a raw score to [0, 1] range.
        
        Args:
            raw_score: The raw score value
            min_val: Expected minimum value
            max_val: Expected maximum value
            
        Returns:
            Score normalized to [0, 1], clamped if out of range
        """
        if max_val == min_val:
            return 0.5
        normalized = (raw_score - min_val) / (max_val - min_val)
        return max(0.0, min(1.0, normalized))
    
    @staticmethod
    def distance_to_score(distance_meters: float, max_distance: float = 10000.0) -> float:
        """
        Convert a distance to a relevance score (closer = higher score).
        
        Args:
            distance_meters: Distance in meters
            max_distance: Maximum distance for scoring (beyond this = 0)
            
        Returns:
            Score in [0, 1] where 0 = max_distance, 1 = 0 distance
        """
        if distance_meters >= max_distance:
            return 0.0
        return 1.0 - (distance_meters / max_distance)
    
    @staticmethod
    def vector_distance_to_score(distance: float) -> float:
        """
        Convert pgvector L2 distance to a similarity score.
        
        pgvector <-> operator returns L2 distance where 0 = identical.
        We convert to a score where 1 = identical.
        
        Args:
            distance: L2 distance from pgvector
            
        Returns:
            Similarity score in [0, 1]
        """
        # For normalized embeddings, L2 distance ranges from 0 to 2
        # Score = 1 - (distance / 2) gives us [0, 1]
        return max(0.0, min(1.0, 1.0 - (distance / 2.0)))

    @staticmethod
    def cosine_distance_to_score(distance: float) -> float:
        """
        Convert pgvector cosine distance to a similarity-like score.

        pgvector <=> returns cosine distance where:
        - 0.0 is identical
        - 1.0 is orthogonal
        - 2.0 is opposite

        We clamp opposite/negative-correlation cases to 0.0 so the score
        remains in [0, 1] with 1.0 representing the best match.
        """
        return max(0.0, min(1.0, 1.0 - distance))
