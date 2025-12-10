"""
DynaTrust-RAG Provenance Builder

Constructs machine-readable provenance records for every answer,
tracking all data sources, queries, and generation steps.

Design Principles:
- Every piece of evidence is traceable to source tables/chunks
- SQL queries are captured for reproducibility
- Provenance is structured for programmatic analysis
"""

from datetime import datetime
from typing import List, Optional

from ..api.schemas import (
    Provenance,
    ProvenanceStep,
    ProvenanceStepType,
    QueryType,
    RowReference,
)


class ProvenanceBuilder:
    """
    Builder for constructing Provenance objects incrementally.
    
    Used throughout the query pipeline to accumulate provenance
    information from each retrieval and generation step.
    
    Example usage:
        builder = ProvenanceBuilder()
        builder.add_step(sql_step)
        builder.add_step(chunk_step)
        provenance = builder.build()
    """
    
    def __init__(self):
        """Initialize an empty provenance builder."""
        self._steps: List[ProvenanceStep] = []
        self._classification: QueryType = QueryType.HYBRID
        self._start_time: datetime = datetime.utcnow()
    
    def add_step(self, step: ProvenanceStep) -> "ProvenanceBuilder":
        """
        Add a provenance step to the chain.
        
        Args:
            step: The ProvenanceStep to add
            
        Returns:
            self for chaining
        """
        self._steps.append(step)
        return self
    
    def add_sql_step(
        self,
        query: str,
        tables: List[str],
        rows: Optional[List[RowReference]] = None,
        execution_time_ms: Optional[float] = None,
    ) -> "ProvenanceBuilder":
        """
        Convenience method to add a SQL retrieval step.
        
        Args:
            query: The SQL query executed
            tables: Tables accessed
            rows: Specific rows that contributed
            execution_time_ms: Query execution time
            
        Returns:
            self for chaining
        """
        step = ProvenanceStep(
            type=ProvenanceStepType.SQL,
            query=query,
            tables=tables,
            rows=rows or [],
            execution_time_ms=execution_time_ms,
        )
        return self.add_step(step)
    
    def add_spatial_step(
        self,
        query: str,
        tables: List[str],
        rows: Optional[List[RowReference]] = None,
        execution_time_ms: Optional[float] = None,
    ) -> "ProvenanceBuilder":
        """
        Convenience method to add a spatial retrieval step.
        
        Args:
            query: The spatial SQL query executed
            tables: Tables accessed
            rows: Specific rows that contributed
            execution_time_ms: Query execution time
            
        Returns:
            self for chaining
        """
        step = ProvenanceStep(
            type=ProvenanceStepType.SPATIAL,
            query=query,
            tables=tables,
            rows=rows or [],
            execution_time_ms=execution_time_ms,
        )
        return self.add_step(step)
    
    def add_chunk_step(
        self,
        chunk_ids: List[str],
        similarity_scores: Optional[List[float]] = None,
        execution_time_ms: Optional[float] = None,
    ) -> "ProvenanceBuilder":
        """
        Convenience method to add a text chunk retrieval step.
        
        Args:
            chunk_ids: IDs of retrieved chunks
            similarity_scores: Similarity scores for each chunk
            execution_time_ms: Retrieval time
            
        Returns:
            self for chaining
        """
        step = ProvenanceStep(
            type=ProvenanceStepType.TEXT_CHUNK,
            chunk_ids=chunk_ids,
            similarity_scores=similarity_scores,
            execution_time_ms=execution_time_ms,
        )
        return self.add_step(step)
    
    def add_llm_step(
        self,
        model_used: str,
        prompt_hash: Optional[str] = None,
        execution_time_ms: Optional[float] = None,
    ) -> "ProvenanceBuilder":
        """
        Add an LLM generation step to provenance.
        
        Args:
            model_used: Identifier of the LLM model
            prompt_hash: Hash of the prompt for reproducibility
            execution_time_ms: Generation time
            
        Returns:
            self for chaining
        """
        step = ProvenanceStep(
            type=ProvenanceStepType.LLM_GENERATION,
            model_used=model_used,
            prompt_hash=prompt_hash,
            execution_time_ms=execution_time_ms,
        )
        return self.add_step(step)
    
    def set_classification(self, query_type: QueryType) -> "ProvenanceBuilder":
        """
        Set the query classification.
        
        Args:
            query_type: How the query was classified
            
        Returns:
            self for chaining
        """
        self._classification = query_type
        return self
    
    def build(self) -> Provenance:
        """
        Build the final Provenance object.
        
        Returns:
            Complete Provenance with all accumulated steps
        """
        # Count totals
        total_rows = 0
        total_chunks = 0
        
        for step in self._steps:
            if step.rows:
                total_rows += len(step.rows)
            if step.chunk_ids:
                total_chunks += len(step.chunk_ids)
        
        return Provenance(
            steps=self._steps,
            total_rows_accessed=total_rows,
            total_chunks_retrieved=total_chunks,
            query_classification=self._classification,
        )
    
    def get_all_tables(self) -> List[str]:
        """Get all tables accessed across all steps."""
        tables = set()
        for step in self._steps:
            if step.tables:
                tables.update(step.tables)
        return list(tables)
    
    def get_all_row_ids(self) -> List[tuple]:
        """Get all (table, id) pairs accessed."""
        row_ids = []
        for step in self._steps:
            if step.rows:
                for row in step.rows:
                    row_ids.append((row.table, row.id))
        return row_ids
    
    def get_all_chunk_ids(self) -> List[str]:
        """Get all chunk IDs retrieved."""
        chunk_ids = []
        for step in self._steps:
            if step.chunk_ids:
                chunk_ids.extend(step.chunk_ids)
        return chunk_ids
