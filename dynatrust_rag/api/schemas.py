"""
DynaTrust-RAG API Schemas

Pydantic models for request/response validation and serialization.
These schemas define the contract for the /dynatrust/query endpoint.

Design Principles:
- Clear separation between request parameters and response structure
- Machine-readable provenance for reproducibility and debugging
- Explicit staleness information for transparency about data freshness
- Extensible structures for future evaluation and metrics
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class QueryType(str, Enum):
    """
    Classification of query types for routing to appropriate retrieval strategy.
    
    - TEXT_ONLY: Pure semantic search over document chunks
    - STRUCTURED: SQL-based filtering on structured columns
    - SPATIAL: Queries involving geographic/geometric predicates
    - HYBRID: Combination of multiple retrieval strategies
    """
    TEXT_ONLY = "text_only"
    STRUCTURED = "structured"
    SPATIAL = "spatial"
    HYBRID = "hybrid"


class ProvenanceStepType(str, Enum):
    """Type of provenance step in the retrieval pipeline."""
    SQL = "sql"
    SPATIAL = "spatial"
    TEXT_CHUNK = "text_chunk"
    LLM_GENERATION = "llm_generation"


# =============================================================================
# Provenance Models
# =============================================================================

class RowReference(BaseModel):
    """
    Reference to a specific row in a database table.
    Used for attribution tracking.
    """
    table: str = Field(..., description="Name of the source table")
    id: Union[str, int] = Field(..., description="Primary key value")
    columns_used: Optional[List[str]] = Field(
        None, 
        description="Which columns from this row contributed to the answer"
    )


class ProvenanceStep(BaseModel):
    """
    A single step in the provenance chain.
    
    Each step represents one retrieval or generation action,
    with full traceability of what data was accessed.
    """
    type: ProvenanceStepType = Field(..., description="Type of this provenance step")
    
    # For SQL/Spatial steps
    query: Optional[str] = Field(
        None, 
        description="The SQL query executed (for SQL/spatial steps)"
    )
    tables: Optional[List[str]] = Field(
        None, 
        description="Tables accessed in this step"
    )
    rows: Optional[List[RowReference]] = Field(
        None, 
        description="Specific rows that contributed to the answer"
    )
    
    # For text chunk steps
    chunk_ids: Optional[List[str]] = Field(
        None, 
        description="IDs of text chunks retrieved (format: doc_id#section_id)"
    )
    similarity_scores: Optional[List[float]] = Field(
        None, 
        description="Similarity scores for retrieved chunks"
    )
    
    # For LLM generation steps
    prompt_hash: Optional[str] = Field(
        None, 
        description="Hash of the prompt sent to LLM (for reproducibility)"
    )
    model_used: Optional[str] = Field(
        None, 
        description="LLM model identifier"
    )
    
    # Timing information
    execution_time_ms: Optional[float] = Field(
        None, 
        description="Time taken for this step in milliseconds"
    )


class Provenance(BaseModel):
    """
    Complete provenance record for an answer.
    
    This structure enables:
    - Full reproducibility of answers
    - Attribution analysis (which sources contributed)
    - Debugging of retrieval and generation
    - Future evaluation of attribution quality
    """
    steps: List[ProvenanceStep] = Field(
        default_factory=list,
        description="Ordered list of provenance steps"
    )
    total_rows_accessed: int = Field(
        0, 
        description="Total number of database rows accessed"
    )
    total_chunks_retrieved: int = Field(
        0, 
        description="Total number of text chunks retrieved"
    )
    query_classification: QueryType = Field(
        QueryType.HYBRID,
        description="How the query was classified for routing"
    )


# =============================================================================
# Staleness Models
# =============================================================================

class StalenessInfo(BaseModel):
    """
    Information about data freshness and vector index staleness.
    
    This structure helps users and downstream systems understand
    whether the answer might be affected by stale embeddings.
    """
    vector_index_lag_seconds: Optional[int] = Field(
        None,
        description="Seconds since the vector index was last refreshed"
    )
    last_vector_refresh_at: Optional[datetime] = Field(
        None,
        description="Timestamp of the last vector index refresh"
    )
    newest_relevant_data_at: Optional[datetime] = Field(
        None,
        description="Timestamp of the most recently updated relevant record"
    )
    used_semantic_results: bool = Field(
        True,
        description="Whether semantic/vector results were used in this answer"
    )
    staleness_detected: bool = Field(
        False,
        description="Whether staleness was detected for this query"
    )
    notes: Optional[str] = Field(
        None,
        description="Human-readable notes about staleness handling"
    )
    semantic_weight_applied: Optional[float] = Field(
        None,
        description="Weight applied to semantic results (may be reduced if stale)"
    )


# =============================================================================
# Request Models
# =============================================================================

class SpatialConstraint(BaseModel):
    """
    Optional spatial constraint for the query.
    """
    latitude: float = Field(..., ge=-90, le=90, description="Center latitude")
    longitude: float = Field(..., ge=-180, le=180, description="Center longitude")
    radius_meters: float = Field(
        1000.0, 
        gt=0, 
        description="Search radius in meters"
    )


class TimeWindow(BaseModel):
    """
    Optional temporal constraint for the query.
    """
    start: Optional[datetime] = Field(None, description="Start of time window")
    end: Optional[datetime] = Field(None, description="End of time window")
    last_n_hours: Optional[int] = Field(
        None, 
        gt=0, 
        description="Alternative: look back N hours from now"
    )


class QueryRequest(BaseModel):
    """
    Request model for the /dynatrust/query endpoint.
    
    Accepts a natural-language question with optional spatial,
    temporal, and filtering constraints.
    """
    question: str = Field(
        ..., 
        min_length=1, 
        max_length=2000,
        description="Natural language question to answer"
    )
    
    # Optional constraints
    spatial: Optional[SpatialConstraint] = Field(
        None, 
        description="Optional spatial constraint (location + radius)"
    )
    time_window: Optional[TimeWindow] = Field(
        None, 
        description="Optional temporal constraint"
    )
    
    # Filtering options
    source_types: Optional[List[str]] = Field(
        None, 
        description="Filter to specific source types"
    )
    entity_ids: Optional[List[str]] = Field(
        None, 
        description="Filter to specific entity IDs"
    )
    
    # Control flags
    include_provenance: bool = Field(
        True, 
        description="Whether to include detailed provenance in response"
    )
    include_staleness_info: bool = Field(
        True, 
        description="Whether to include staleness information"
    )
    force_live_data_only: bool = Field(
        False, 
        description="If true, skip semantic search and use only live SQL/spatial"
    )
    
    # For evaluation/debugging
    session_id: Optional[str] = Field(
        None, 
        description="Optional session ID for query grouping"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "What anomalies were detected near the port in the last 24 hours?",
                "spatial": {
                    "latitude": 42.4833,
                    "longitude": 27.4833,
                    "radius_meters": 5000
                },
                "time_window": {
                    "last_n_hours": 24
                },
                "include_provenance": True
            }
        }


# =============================================================================
# Response Models
# =============================================================================

class QueryResponse(BaseModel):
    """
    Response model for the /dynatrust/query endpoint.
    
    Contains the answer along with full provenance and staleness information
    for transparency and reproducibility.
    """
    # Core response
    answer: str = Field(..., description="Natural language answer to the question")
    
    # Attribution and transparency
    provenance: Optional[Provenance] = Field(
        None, 
        description="Detailed provenance of how the answer was derived"
    )
    staleness_info: Optional[StalenessInfo] = Field(
        None, 
        description="Information about data freshness"
    )
    
    # Metadata
    query_id: str = Field(..., description="Unique identifier for this query")
    query_type: QueryType = Field(
        ..., 
        description="How the query was classified"
    )
    processing_time_ms: float = Field(
        ..., 
        description="Total processing time in milliseconds"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the query was processed"
    )
    
    # For evaluation
    confidence_score: Optional[float] = Field(
        None, 
        ge=0.0, 
        le=1.0,
        description="Confidence in the answer (0-1)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "answer": "There were 3 anomalies detected near the port in the last 24 hours: 2 trajectory deviations and 1 speed anomaly.",
                "query_id": "q_abc123",
                "query_type": "hybrid",
                "processing_time_ms": 245.3,
                "provenance": {
                    "steps": [
                        {
                            "type": "spatial",
                            "query": "SELECT ... ST_DWithin(...)",
                            "tables": ["observations_core", "anomalies"],
                            "rows": [
                                {"table": "anomalies", "id": 42},
                                {"table": "anomalies", "id": 43}
                            ]
                        }
                    ],
                    "total_rows_accessed": 5,
                    "query_classification": "hybrid"
                },
                "staleness_info": {
                    "vector_index_lag_seconds": 1800,
                    "used_semantic_results": True,
                    "staleness_detected": False
                }
            }
        }
