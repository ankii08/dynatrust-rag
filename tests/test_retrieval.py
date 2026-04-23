"""Tests for retrieval components."""

import uuid
from contextlib import asynccontextmanager

import pytest

from dynatrust_rag.api.schemas import QueryRequest, QueryType, SpatialConstraint
from dynatrust_rag.retrieval.base import (
    BaseRetriever,
    DocumentChunk,
    RetrievalResult,
    SpatialRow,
    StructuredRow,
)
from dynatrust_rag.retrieval.router import QueryClassifier, HybridRetrievalRouter
from dynatrust_rag.retrieval.spatial import SpatialRetriever
from dynatrust_rag.retrieval.structured import StructuredRetriever


class TestRetrievalResult:
    def test_empty_result(self):
        result = RetrievalResult()
        assert result.total_results == 0
        assert result.is_empty is True

    def test_total_results(self):
        result = RetrievalResult(
            semantic_chunks=[
                DocumentChunk(id=1, chunk_id="d#0", text="t", score=0.5, source_doc="d")
            ],
            structured_rows=[
                StructuredRow(table_name="assets", primary_key=1, data={"name": "x"})
            ],
        )
        assert result.total_results == 2
        assert result.is_empty is False

    def test_merge(self):
        r1 = RetrievalResult(
            semantic_chunks=[
                DocumentChunk(id=1, chunk_id="d#0", text="t", score=0.5, source_doc="d")
            ],
            metadata={"retrievers_used": ["semantic"]},
        )
        r2 = RetrievalResult(
            structured_rows=[
                StructuredRow(table_name="assets", primary_key=1, data={})
            ],
            metadata={"retrievers_used": ["structured"]},
        )
        merged = r1.merge(r2)
        assert len(merged.semantic_chunks) == 1
        assert len(merged.structured_rows) == 1
        assert set(merged.metadata["retrievers_used"]) == {"semantic", "structured"}

    def test_get_chunk_ids(self):
        result = RetrievalResult(
            semantic_chunks=[
                DocumentChunk(id=1, chunk_id="doc1#chunk_0", text="t", score=0.5, source_doc="d"),
                DocumentChunk(id=2, chunk_id="doc1#chunk_1", text="t", score=0.4, source_doc="d"),
            ],
        )
        assert result.get_chunk_ids() == ["doc1#chunk_0", "doc1#chunk_1"]

    def test_get_row_references(self):
        result = RetrievalResult(
            spatial_rows=[
                SpatialRow(table_name="points", primary_key=5, score=0.8)
            ],
        )
        refs = result.get_row_references()
        assert len(refs) == 1
        assert refs[0]["table"] == "points"
        assert refs[0]["id"] == 5


class TestBaseRetrieverHelpers:
    def test_normalize_score(self):
        assert BaseRetriever.normalize_score(0.5, 0.0, 1.0) == 0.5
        assert BaseRetriever.normalize_score(0.0, 0.0, 1.0) == 0.0
        assert BaseRetriever.normalize_score(1.0, 0.0, 1.0) == 1.0
        # Clamping
        assert BaseRetriever.normalize_score(-0.5, 0.0, 1.0) == 0.0
        assert BaseRetriever.normalize_score(1.5, 0.0, 1.0) == 1.0

    def test_distance_to_score(self):
        assert BaseRetriever.distance_to_score(0.0) == 1.0
        assert BaseRetriever.distance_to_score(10000.0) == 0.0
        assert 0 < BaseRetriever.distance_to_score(5000.0) < 1

    def test_vector_distance_to_score(self):
        assert BaseRetriever.vector_distance_to_score(0.0) == 1.0
        assert BaseRetriever.vector_distance_to_score(2.0) == 0.0
        assert 0 < BaseRetriever.vector_distance_to_score(1.0) < 1


class TestQueryClassifier:
    def setup_method(self):
        self.classifier = QueryClassifier()

    def test_text_only_query(self):
        req = QueryRequest(question="What is DynaTrust-RAG?")
        result = self.classifier.classify(req)
        assert result.query_type == QueryType.TEXT_ONLY
        assert result.use_semantic is True
        assert result.use_spatial is False
        assert result.use_structured is False

    def test_spatial_keyword_detection(self):
        req = QueryRequest(question="What happened near the port?")
        result = self.classifier.classify(req)
        assert result.use_spatial is True

    def test_spatial_phrase_detection(self):
        req = QueryRequest(question="What happened close to the port?")
        result = self.classifier.classify(req)
        assert result.use_spatial is True

    def test_spatial_with_explicit_constraint(self):
        req = QueryRequest(
            question="Show anomalies",
            spatial=SpatialConstraint(latitude=42.5, longitude=27.5, radius_meters=1000),
        )
        result = self.classifier.classify(req)
        assert result.use_spatial is True
        assert "explicit_spatial_constraint" in result.signals

    def test_structured_year_detection(self):
        req = QueryRequest(question="Assets installed after 2022")
        result = self.classifier.classify(req)
        assert result.use_structured is True

    def test_structured_keyword_detection(self):
        req = QueryRequest(question="Show all assets with status active")
        result = self.classifier.classify(req)
        assert result.use_structured is True

    def test_structured_phrase_detection(self):
        req = QueryRequest(question="How many active assets are there?")
        result = self.classifier.classify(req)
        assert result.use_structured is True

    def test_hybrid_classification(self):
        req = QueryRequest(
            question="What happened near the port after 2022?",
            spatial=SpatialConstraint(latitude=42.5, longitude=27.5, radius_meters=5000),
        )
        result = self.classifier.classify(req)
        assert result.query_type == QueryType.HYBRID
        assert result.use_semantic is True
        assert result.use_spatial is True
        assert result.use_structured is True

    def test_force_live_data_disables_semantic(self):
        req = QueryRequest(question="What is Atlas4D?", force_live_data_only=True)
        result = self.classifier.classify(req)
        assert result.use_semantic is False

    def test_confidence_increases_with_signals(self):
        simple = QueryRequest(question="Hello")
        complex_ = QueryRequest(
            question="Assets near the port installed after 2020",
            spatial=SpatialConstraint(latitude=42.5, longitude=27.5, radius_meters=1000),
        )
        c1 = self.classifier.classify(simple)
        c2 = self.classifier.classify(complex_)
        assert c2.confidence >= c1.confidence


class TestLiveRowPrimaryKeys:
    @pytest.mark.asyncio
    async def test_structured_retriever_converts_uuid_primary_keys(self, monkeypatch):
        record = {
            "id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
            "install_date": "2024-06-09",
            "name": "BG-SW-CENTRAL-02",
            "status": "active",
            "asset_type": "distribution_switch",
            "location": "Burgas Central",
        }

        class FakeConn:
            async def fetch(self, sql, *params):
                return [record]

        @asynccontextmanager
        async def fake_get_connection():
            yield FakeConn()

        monkeypatch.setattr("dynatrust_rag.retrieval.structured.get_connection", fake_get_connection)

        result = await StructuredRetriever().retrieve(
            QueryRequest(question="Show assets installed after 2022 that are active."),
            limit=20,
        )

        assert len(result.structured_rows) == 1
        assert result.structured_rows[0].primary_key == "22222222-2222-2222-2222-222222222222"

    @pytest.mark.asyncio
    async def test_spatial_retriever_converts_uuid_primary_keys(self, monkeypatch):
        record = {
            "id": uuid.UUID("aaaaaaa1-aaaa-aaaa-aaaa-aaaaaaaaaaa1"),
            "wkt": "POINT(27.4678 42.4926)",
            "distance_meters": 73.0,
            "name": "Burgas Port Fiber Hub",
            "point_type": "telecom_site",
            "description": "Fiber aggregation hub serving the port.",
            "metadata": {"demo_seed": "live_demo"},
            "created_at": "2026-04-22T00:00:00Z",
            "geom": object(),
        }

        class FakeConn:
            async def fetch(self, sql, *params):
                return [record]

        @asynccontextmanager
        async def fake_get_connection():
            yield FakeConn()

        monkeypatch.setattr("dynatrust_rag.retrieval.spatial.get_connection", fake_get_connection)

        result = await SpatialRetriever().retrieve(
            QueryRequest(
                question="What telecom sites are near Burgas port?",
                spatial=SpatialConstraint(latitude=42.4930, longitude=27.4685, radius_meters=1500),
            ),
            limit=20,
        )

        assert len(result.spatial_rows) == 1
        assert result.spatial_rows[0].primary_key == "aaaaaaa1-aaaa-aaaa-aaaa-aaaaaaaaaaa1"
