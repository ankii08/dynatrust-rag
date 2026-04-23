"""Tests for API router orchestration and provenance construction."""

import pytest

from dynatrust_rag.api.schemas import QueryRequest, QueryType, StalenessInfo
from dynatrust_rag.retrieval.base import DocumentChunk, RetrievalResult, StructuredRow
from dynatrust_rag.api import router as api_router


def test_build_provenance_uses_correct_sql_and_classification():
    result = RetrievalResult(
        semantic_chunks=[
            DocumentChunk(
                id=1,
                chunk_id="doc#chunk_0",
                text="chunk text",
                score=0.9,
                source_doc="doc.md",
            )
        ],
        structured_rows=[
            StructuredRow(
                table_name="assets",
                primary_key="asset-1",
                data={"name": "Tower 1"},
            )
        ],
        executed_sql=[
            "SELECT * FROM dynatrust.document_chunks ORDER BY embedding <=> '[...]'::vector",
            "SELECT * FROM dynatrust.assets WHERE status = 'active'",
        ],
        metadata={
            "retrievers_used": ["semantic", "structured"],
            "query_type": "hybrid",
            "sql_by_retriever": {
                "semantic": [
                    "SELECT * FROM dynatrust.document_chunks ORDER BY embedding <=> '[...]'::vector"
                ],
                "structured": [
                    "SELECT * FROM dynatrust.assets WHERE status = 'active'"
                ],
            },
        },
    )

    provenance = api_router._build_provenance(result)

    structured_step = next(step for step in provenance.steps if step.type.value == "sql")
    assert structured_step.query == "SELECT * FROM dynatrust.assets WHERE status = 'active'"
    assert provenance.query_classification == QueryType.HYBRID


@pytest.mark.asyncio
async def test_query_endpoint_disables_semantic_when_staleness_requires_it(monkeypatch):
    captured = {}

    async def fake_hybrid_retrieve(request, limit=20):
        captured["force_live_data_only"] = request.force_live_data_only
        return RetrievalResult(
            structured_rows=[
                StructuredRow(
                    table_name="assets",
                    primary_key="asset-1",
                    data={"name": "Tower 1", "status": "active"},
                )
            ],
            executed_sql=["SELECT * FROM dynatrust.assets WHERE status = 'active'"],
            metadata={
                "retrievers_used": ["structured"],
                "query_type": "structured",
                "sql_by_retriever": {
                    "structured": [
                        "SELECT * FROM dynatrust.assets WHERE status = 'active'"
                    ]
                },
            },
        )

    async def fake_check_staleness(self, request):
        return StalenessInfo(
            vector_index_lag_seconds=100000,
            used_semantic_results=False,
            staleness_detected=True,
            notes="semantic disabled for stale index",
        )

    async def fake_generate(request, result, provenance, staleness_info):
        return "answer", False

    class DummyLogger:
        def __init__(self, config):
            self.config = config

        async def log_query(self, query_id, request, response):
            return True

    monkeypatch.setattr(api_router, "hybrid_retrieve", fake_hybrid_retrieve)
    monkeypatch.setattr(api_router.StalenessTracker, "check_staleness", fake_check_staleness)
    monkeypatch.setattr(api_router, "_generate_llm_answer", fake_generate)
    monkeypatch.setattr(api_router, "QueryLogger", DummyLogger)

    response = await api_router.query_endpoint(
        QueryRequest(question="How many active assets are there?")
    )

    assert captured["force_live_data_only"] is True
    assert response.query_type == QueryType.STRUCTURED
    assert response.staleness_info is not None
    assert response.staleness_info.used_semantic_results is False
