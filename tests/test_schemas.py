"""Tests for Pydantic API schemas."""

import pytest
from pydantic import ValidationError

from dynatrust_rag.api.schemas import (
    QueryRequest,
    QueryResponse,
    QueryType,
    Provenance,
    ProvenanceStep,
    ProvenanceStepType,
    RowReference,
    StalenessInfo,
    SpatialConstraint,
    TimeWindow,
)


class TestQueryRequest:
    def test_minimal_request(self):
        req = QueryRequest(question="What is Atlas4D?")
        assert req.question == "What is Atlas4D?"
        assert req.include_provenance is True  # default

    def test_whitespace_stripped(self):
        req = QueryRequest(question="  What is Atlas4D?  ")
        assert req.question == "What is Atlas4D?"

    def test_empty_question_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(question="")

    def test_question_too_long_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(question="x" * 2001)

    def test_spatial_constraint_validation(self):
        req = QueryRequest(
            question="nearby assets",
            spatial=SpatialConstraint(latitude=42.5, longitude=27.5, radius_meters=5000),
        )
        assert req.spatial.latitude == 42.5

    def test_spatial_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(
                question="nearby assets",
                spatial=SpatialConstraint(latitude=91.0, longitude=0, radius_meters=100),
            )

    def test_negative_radius_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(
                question="nearby assets",
                spatial=SpatialConstraint(latitude=0, longitude=0, radius_meters=-100),
            )


class TestProvenance:
    def test_provenance_with_all_fields(self):
        prov = Provenance(
            steps=[
                ProvenanceStep(
                    type=ProvenanceStepType.TEXT_CHUNK,
                    chunk_ids=["doc1#chunk_0"],
                    similarity_scores=[0.85],
                )
            ],
            source_docs=["doc1.md"],
            sql_executed=["SELECT * FROM chunks"],
            row_references=[RowReference(table="assets", id=42)],
            total_chunks_retrieved=1,
            total_rows_accessed=1,
        )
        assert len(prov.steps) == 1
        assert prov.source_docs == ["doc1.md"]
        assert prov.sql_executed == ["SELECT * FROM chunks"]
        assert prov.total_chunks_retrieved == 1

    def test_provenance_defaults(self):
        prov = Provenance()
        assert prov.steps == []
        assert prov.source_docs == []
        assert prov.sql_executed == []
        assert prov.row_references == []


class TestStalenessInfo:
    def test_staleness_fields(self):
        info = StalenessInfo(
            vector_index_lag_seconds=120,
            used_semantic_results=True,
            staleness_detected=False,
            notes="fresh",
        )
        assert info.vector_index_lag_seconds == 120
        assert info.staleness_detected is False

    def test_staleness_defaults(self):
        info = StalenessInfo()
        assert info.used_semantic_results is True
        assert info.staleness_detected is False
