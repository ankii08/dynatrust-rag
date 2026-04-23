"""
DynaTrust-RAG Semantic Retriever

Implements vector similarity search using pgvector for semantic retrieval
over document chunks stored in PostgreSQL.

How it works:
1. Takes the question text from QueryRequest
2. Computes an embedding vector using EmbeddingProvider
3. Runs a pgvector similarity query against dynatrust.document_chunks
4. Returns DocumentChunk objects with similarity scores
5. Logs the executed SQL for provenance

Table schema (from 002_dynatrust_rag.sql):
    dynatrust.document_chunks (
        id              SERIAL PRIMARY KEY,
        doc_id          TEXT NOT NULL,
        chunk_index     INTEGER NOT NULL,
        content         TEXT NOT NULL,
        source_type     TEXT DEFAULT 'documentation',
        metadata        JSONB DEFAULT '{}',
        embedding       VECTOR(768),
        created_at      TIMESTAMPTZ,
        updated_at      TIMESTAMPTZ
    )
"""

import logging
from typing import List, Optional

from ..api.schemas import QueryRequest
from ..db.connection import get_connection
from ..embedding import get_default_embedding_provider, EMBEDDING_DIM
from .base import BaseRetriever, DocumentChunk, RetrievalResult


logger = logging.getLogger(__name__)

# Default number of results
DEFAULT_K = 10


class SemanticRetriever(BaseRetriever):
    """
    Semantic retriever using pgvector for embedding-based similarity search.
    
    Retrieves document chunks based on semantic similarity to the query,
    using pre-computed embeddings stored in PostgreSQL with pgvector.
    
    Features:
    - Uses EmbeddingProvider for query embeddings (OpenAI or local)
    - Configurable number of results (k)
    - Filters by source_type if specified in QueryRequest
    - Tracks executed SQL for provenance
    - Converts vector distance to similarity score [0, 1]
    
    Example usage:
        retriever = SemanticRetriever()
        result = await retriever.retrieve(query_request, limit=10)
        for chunk in result.semantic_chunks:
            print(f"{chunk.chunk_id}: {chunk.text[:100]}... (score: {chunk.score})")
    """
    
    def __init__(self, pool=None, default_k: int = DEFAULT_K):
        """
        Initialize the semantic retriever.
        
        Args:
            pool: Optional asyncpg connection pool
            default_k: Default number of results to retrieve
        """
        super().__init__(pool)
        self.default_k = default_k
        self._embedding_provider = None
    
    async def _get_embedding_provider(self):
        """Get or initialize the embedding provider."""
        if self._embedding_provider is None:
            self._embedding_provider = await get_default_embedding_provider()
        return self._embedding_provider
    
    async def retrieve(self, query: QueryRequest, limit: int = 10) -> RetrievalResult:
        """
        Retrieve semantically similar document chunks.
        
        Args:
            query: QueryRequest containing the question and optional filters
            limit: Maximum number of chunks to retrieve
            
        Returns:
            RetrievalResult with semantic_chunks populated and executed_sql logged
        """
        k = min(limit, self.MAX_LIMIT)
        
        # Get the query embedding using the configured provider
        question_text = query.question
        provider = await self._get_embedding_provider()
        
        try:
            query_embedding = await provider.embed_text(question_text)
            logger.debug(f"Generated query embedding with {len(query_embedding)} dimensions")
        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}")
            return RetrievalResult(
                semantic_chunks=[],
                executed_sql=[],
                metadata={
                    "retrievers_used": ["semantic"],
                    "error": f"Embedding generation failed: {e}",
                },
            )
        
        # Convert embedding to string format for SQL
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
        
        # Build the SQL query.
        # The schema index uses vector_cosine_ops, so we query with <=> to
        # ensure PostgreSQL can use the ANN index.
        
        if query.source_types:
            # Filter by source types
            sql = """
                SELECT 
                    id,
                    doc_id,
                    chunk_index,
                    content,
                    source_type,
                    metadata,
                    embedding <=> $1::vector AS distance
                FROM dynatrust.document_chunks
                WHERE source_type = ANY($2)
                ORDER BY embedding <=> $1::vector
                LIMIT $3
            """
            params = [embedding_str, query.source_types, k]
            sql_for_provenance = f"""
                SELECT id, doc_id, chunk_index, content, source_type, metadata,
                       embedding <=> '[...]'::vector AS distance
                FROM dynatrust.document_chunks
                WHERE source_type = ANY({query.source_types})
                ORDER BY embedding <=> '[...]'::vector
                LIMIT {k}
            """
        else:
            sql = """
                SELECT 
                    id,
                    doc_id,
                    chunk_index,
                    content,
                    source_type,
                    metadata,
                    embedding <=> $1::vector AS distance
                FROM dynatrust.document_chunks
                ORDER BY embedding <=> $1::vector
                LIMIT $2
            """
            params = [embedding_str, k]
            sql_for_provenance = f"""
                SELECT id, doc_id, chunk_index, content, source_type, metadata,
                       embedding <=> '[...]'::vector AS distance
                FROM dynatrust.document_chunks
                ORDER BY embedding <=> '[...]'::vector
                LIMIT {k}
            """
        
        # Execute the query
        chunks: List[DocumentChunk] = []
        
        try:
            async with get_connection() as conn:
                rows = await conn.fetch(sql, *params)
                
                for row in rows:
                    # Convert cosine distance to a similarity score [0, 1].
                    distance = float(row["distance"])
                    score = self.cosine_distance_to_score(distance)
                    
                    # Build chunk ID
                    chunk_id = f"{row['doc_id']}#chunk_{row['chunk_index']}"
                    
                    # Parse metadata - handle both dict and JSON string
                    raw_meta = row["metadata"]
                    if raw_meta is None:
                        metadata = {}
                    elif isinstance(raw_meta, dict):
                        metadata = raw_meta
                    elif isinstance(raw_meta, str):
                        import json
                        try:
                            metadata = json.loads(raw_meta)
                        except json.JSONDecodeError:
                            metadata = {}
                    else:
                        metadata = {}
                    metadata["source_type"] = row["source_type"]
                    metadata["distance"] = distance
                    
                    chunk = DocumentChunk(
                        id=row["id"],
                        chunk_id=chunk_id,
                        text=row["content"],
                        score=score,
                        source_doc=row["doc_id"],
                        section=metadata.get("section"),
                        metadata=metadata,
                    )
                    chunks.append(chunk)
                    
        except Exception as e:
            # Log error but don't fail - return empty results
            print(f"[SemanticRetriever] Error during retrieval: {e}")
            return RetrievalResult(
                semantic_chunks=[],
                executed_sql=[sql_for_provenance],
                metadata={
                    "retrievers_used": ["semantic"],
                    "error": str(e),
                },
            )
        
        return RetrievalResult(
            semantic_chunks=chunks,
            executed_sql=[sql_for_provenance],
            metadata={
                "retrievers_used": ["semantic"],
                "chunks_retrieved": len(chunks),
                "distance_metric": "cosine",
            },
        )
    
    async def health_check(self) -> bool:
        """
        Check if pgvector is accessible and the document_chunks table exists.
        
        Returns:
            True if healthy and ready to serve queries
        """
        try:
            async with get_connection() as conn:
                # Check vector extension
                result = await conn.fetchval(
                    "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                )
                if result != 1:
                    return False
                
                # Check table exists
                result = await conn.fetchval("""
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_schema = 'dynatrust' 
                    AND table_name = 'document_chunks'
                """)
                return result == 1
                
        except Exception:
            return False
