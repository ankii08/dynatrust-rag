"""
DynaTrust RAG API Router

Exposes /dynatrust/query endpoint that orchestrates hybrid retrieval
and returns provenance-rich responses.

Flow:
1. Classify query and run hybrid retrieval (semantic + spatial + structured)
2. Check staleness of vector index
3. Generate LLM-powered answer with provenance
4. Log query for evaluation
5. Return response with full attribution
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from .schemas import (
    QueryRequest,
    QueryResponse,
    QueryType,
    Provenance,
    ProvenanceStep,
    ProvenanceStepType,
    RowReference,
    StalenessInfo,
)
from ..retrieval.router import hybrid_retrieve
from ..retrieval.base import RetrievalResult
from ..llm.answerer import AnswerGenerator, get_answer_generator as _get_answer_generator

logger = logging.getLogger(__name__)


dynatrust_router = APIRouter(prefix="/dynatrust", tags=["DynaTrust RAG"])


def _build_provenance(result: RetrievalResult) -> Provenance:
    """Convert RetrievalResult into a Provenance object for the response."""
    steps: list[ProvenanceStep] = []
    row_refs: list[RowReference] = []

    # Add retrieval step for each retriever used
    for retriever_name in result.metadata.get("retrievers_used", []):
        # Map retriever name to ProvenanceStepType
        if retriever_name == "semantic":
            step_type = ProvenanceStepType.TEXT_CHUNK
            chunk_ids = [chunk.chunk_id for chunk in result.semantic_chunks]
            scores = [chunk.score or 0.0 for chunk in result.semantic_chunks]
            steps.append(
                ProvenanceStep(
                    type=step_type,
                    chunk_ids=chunk_ids if chunk_ids else None,
                    similarity_scores=scores if scores else None,
                )
            )
        elif retriever_name == "spatial":
            step_type = ProvenanceStepType.SPATIAL
            steps.append(
                ProvenanceStep(
                    type=step_type,
                    tables=list({r.table_name for r in result.spatial_rows}),
                )
            )
        elif retriever_name == "structured":
            step_type = ProvenanceStepType.SQL
            steps.append(
                ProvenanceStep(
                    type=step_type,
                    query=result.executed_sql[0] if result.executed_sql else None,
                    tables=list({r.table_name for r in result.structured_rows}),
                )
            )

    # Collect row references from structured rows
    for row in result.structured_rows:
        row_refs.append(
            RowReference(
                table=row.table_name,
                id=row.primary_key,
                columns_used=list(row.data.keys()) if row.data else [],
            )
        )

    # Collect row references from spatial rows
    for row in result.spatial_rows:
        row_refs.append(
            RowReference(
                table=row.table_name,
                id=row.primary_key,
                columns_used=list(row.data.keys()) if row.data else [],
            )
        )

    # Build source docs from semantic chunks
    source_docs = list(
        {chunk.source_doc for chunk in result.semantic_chunks if chunk.source_doc}
    )

    return Provenance(
        source_docs=source_docs,
        row_references=row_refs,
        sql_executed=result.executed_sql,
        steps=steps,
    )


def _build_answer_summary(result: RetrievalResult) -> str:
    """
    Build a fallback text answer summarizing retrieved items.
    Used when LLM is unavailable or disabled.
    """
    parts: list[str] = []

    if result.semantic_chunks:
        parts.append(f"Found {len(result.semantic_chunks)} relevant document chunks.")
        # Include top chunk preview
        top_chunk = result.semantic_chunks[0]
        preview = top_chunk.text[:200] + "..." if len(top_chunk.text) > 200 else top_chunk.text
        parts.append(f"Top match (score={top_chunk.score:.3f}): {preview}")

    if result.structured_rows:
        parts.append(f"Found {len(result.structured_rows)} structured database rows.")

    if result.spatial_rows:
        parts.append(f"Found {len(result.spatial_rows)} spatial results.")
        # Show nearest
        if result.spatial_rows:
            nearest = min(result.spatial_rows, key=lambda r: r.distance_meters or float("inf"))
            if nearest.distance_meters is not None:
                parts.append(f"Nearest result: {nearest.distance_meters:.1f}m away.")

    if not parts:
        return "No relevant information found for your query."

    return " ".join(parts)


async def _generate_llm_answer(
    request: QueryRequest,
    result: RetrievalResult,
    provenance: Provenance,
    staleness_info: StalenessInfo,
) -> tuple[str, bool]:
    """
    Generate an LLM-powered answer from retrieval results.
    
    Args:
        request: The QueryRequest
        result: RetrievalResult from hybrid retrieval
        provenance: Provenance information
        staleness_info: Staleness info for the vector index
        
    Returns:
        Tuple of (answer_text, used_llm)
    """
    # Check if LLM is enabled
    if os.environ.get("DYNATRUST_DISABLE_LLM", "").lower() in ("1", "true"):
        return _build_answer_summary(result), False
    
    try:
        generator = await _get_answer_generator()
        answer = await generator.generate_answer(
            query=request,
            retrieval=result,
            provenance=provenance,
            staleness=staleness_info,
        )
        return answer, True
    except Exception as e:
        logger.warning(f"LLM generation failed, falling back to summary: {e}")
        return _build_answer_summary(result), False


def _build_staleness_info(result: RetrievalResult) -> StalenessInfo:
    """
    Build staleness info from retrieval metadata.
    In production, this would query vector_index_metadata table.
    """
    # Check if metadata contains staleness info
    index_ts = result.metadata.get("index_last_updated")
    data_ts = result.metadata.get("data_last_modified")

    if index_ts and data_ts:
        lag_seconds = (data_ts - index_ts).total_seconds()
        is_stale = lag_seconds > 300  # Consider stale if > 5 minutes lag
    else:
        # Default to current time if no metadata
        index_ts = datetime.now(timezone.utc)
        data_ts = datetime.now(timezone.utc)
        lag_seconds = 0.0
        is_stale = False

    return StalenessInfo(
        is_stale=is_stale,
        index_last_updated=index_ts if isinstance(index_ts, datetime) else datetime.now(timezone.utc),
        data_last_modified=data_ts if isinstance(data_ts, datetime) else datetime.now(timezone.utc),
        lag_seconds=lag_seconds,
    )


@dynatrust_router.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest) -> QueryResponse:
    """
    Main RAG query endpoint.

    Flow:
    1. Classify query and run hybrid retrieval (semantic + spatial + structured)
    2. Generate LLM-powered answer with full provenance
    3. Build staleness info and debug metadata
    4. Return response with attribution

    Example request:
        POST /dynatrust/query
        {
            "question": "What telecom anomalies happened near Burgas in 2023?",
            "spatial": {"latitude": 42.5048, "longitude": 27.4626, "radius_meters": 5000},
            "include_provenance": true
        }

    Example response:
        {
            "query_id": "550e8400-e29b-41d4-a716-446655440000",
            "answer": "Based on the retrieved data, there were 3 telecom anomalies...",
            "query_type": "hybrid",
            "processing_time_ms": 245.3,
            "provenance": {
                "source_docs": ["telecom_report_2023.pdf"],
                "row_references": [{"table": "atlas4d.anomalies", "id": 42}],
                "sql_executed": ["SELECT * FROM atlas4d.anomalies WHERE ..."],
                "steps": [...]
            },
            "staleness_info": {"is_stale": false, ...}
        }
    """
    start_time = time.time()
    query_id = str(uuid.uuid4())
    
    try:
        # Run hybrid retrieval - pass the whole request, not just the query text
        result: RetrievalResult = await hybrid_retrieve(request)

        # Determine query type from result metadata
        retrievers = result.metadata.get("retrievers_used", [])
        if len(retrievers) > 1:
            query_type = QueryType.HYBRID
        elif "spatial" in retrievers:
            query_type = QueryType.SPATIAL
        elif "structured" in retrievers:
            query_type = QueryType.STRUCTURED
        else:
            query_type = QueryType.TEXT_ONLY

        # Build provenance and staleness info first (needed for LLM)
        provenance = _build_provenance(result)
        staleness_info = _build_staleness_info(result)
        
        # Generate LLM-powered answer (with fallback)
        answer, used_llm = await _generate_llm_answer(request, result, provenance, staleness_info)

        # Calculate processing time
        processing_time_ms = (time.time() - start_time) * 1000

        # Build debug info if requested
        debug: dict[str, Any] | None = None
        if request.include_provenance:
            debug = {
                "retrievers_used": result.metadata.get("retrievers_used", []),
                "semantic_chunk_count": len(result.semantic_chunks),
                "structured_row_count": len(result.structured_rows),
                "spatial_row_count": len(result.spatial_rows),
                "query_classification": result.metadata.get("query_type"),
                "used_llm": used_llm,
            }

        response = QueryResponse(
            query_id=query_id,
            answer=answer,
            query_type=query_type,
            processing_time_ms=processing_time_ms,
            provenance=provenance,
            staleness_info=staleness_info,
        )
        
        logger.info(
            f"Query {query_id}: {query_type.value} | "
            f"chunks={len(result.semantic_chunks)} rows={len(result.structured_rows)} "
            f"spatial={len(result.spatial_rows)} | {processing_time_ms:.1f}ms"
        )
        
        return response

    except Exception as e:
        logger.exception(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@dynatrust_router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for the DynaTrust RAG service."""
    return {"status": "ok", "service": "dynatrust-rag"}
