"""
DynaTrust-RAG Configuration Module

Centralized configuration management for the DynaTrust-RAG system.
Supports environment variable overrides for all settings.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DatabaseConfig:
    """PostgreSQL/PostGIS database configuration."""
    host: str = field(default_factory=lambda: os.getenv("POSTGRES_HOST", "postgres"))
    port: int = field(default_factory=lambda: int(os.getenv("POSTGRES_PORT", "5432")))
    database: str = field(default_factory=lambda: os.getenv("POSTGRES_DB", "atlas4d"))
    user: str = field(default_factory=lambda: os.getenv("POSTGRES_USER", "atlas4d_app"))
    password: str = field(default_factory=lambda: os.getenv("PGPASSWORD", "atlas4d_dev"))
    
    @property
    def dsn(self) -> str:
        """Return the database connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class VectorConfig:
    """Configuration for pgvector semantic search."""
    embedding_dim: int = 768
    similarity_threshold: float = 0.7
    max_results: int = 10
    # Staleness threshold in seconds - if vector index is older than this,
    # consider it stale
    staleness_threshold_seconds: int = 3600  # 1 hour default


@dataclass
class EmbeddingConfig:
    """Configuration for the embedding provider."""
    provider: str = field(
        default_factory=lambda: os.getenv("DYNATRUST_EMBEDDING_PROVIDER", "openai")
    )
    model: str = field(
        default_factory=lambda: os.getenv("DYNATRUST_EMBEDDING_MODEL", "text-embedding-3-small")
    )
    dimension: int = 768  # Must match VectorConfig.embedding_dim
    openai_api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )


@dataclass
class SpatialConfig:
    """Configuration for PostGIS spatial queries."""
    default_radius_meters: float = 1000.0
    default_srid: int = 4326
    max_results: int = 100


@dataclass
class RetrievalConfig:
    """Configuration for the hybrid retrieval system."""
    # Weights for combining different retrieval strategies
    semantic_weight: float = 0.4
    spatial_weight: float = 0.3
    structured_weight: float = 0.3
    
    # When staleness is detected, how much to downweight semantic results
    stale_semantic_penalty: float = 0.5
    
    # Threshold for completely disabling semantic results when very stale
    max_staleness_for_semantic_seconds: int = 86400  # 24 hours


@dataclass
class EvaluationConfig:
    """Configuration for evaluation and logging."""
    enable_query_logging: bool = True
    log_provenance: bool = True
    log_staleness_info: bool = True


@dataclass
class DynaTrustConfig:
    """
    Master configuration for DynaTrust-RAG.
    
    All sub-configs can be overridden via environment variables.
    """
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    vector: VectorConfig = field(default_factory=VectorConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    spatial: SpatialConfig = field(default_factory=SpatialConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    
    # LLM configuration (for answer generation)
    llm_model: str = field(default_factory=lambda: os.getenv("DYNATRUST_LLM_MODEL", "gpt-4"))
    llm_temperature: float = field(default_factory=lambda: float(os.getenv("DYNATRUST_LLM_TEMP", "0.1")))


# Global configuration instance
config = DynaTrustConfig()


def get_config() -> DynaTrustConfig:
    """Get the global configuration instance."""
    return config
