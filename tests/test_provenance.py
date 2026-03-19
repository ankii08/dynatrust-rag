"""Tests for provenance tracking and attribution metrics."""

import pytest

from dynatrust_rag.api.schemas import (
    Provenance,
    ProvenanceStep,
    ProvenanceStepType,
    QueryType,
    RowReference,
)
from dynatrust_rag.attribution.provenance import ProvenanceBuilder
from dynatrust_rag.attribution.metrics import AttributionMetrics, AttributionReport


class TestProvenanceBuilder:
    def test_empty_build(self):
        builder = ProvenanceBuilder()
        prov = builder.build()
        assert isinstance(prov, Provenance)
        assert prov.steps == []

    def test_add_sql_step(self):
        builder = ProvenanceBuilder()
        builder.add_sql_step(
            query="SELECT * FROM assets",
            tables=["assets"],
            rows=[RowReference(table="assets", id=1)],
        )
        prov = builder.build()
        assert len(prov.steps) == 1
        assert prov.steps[0].type == ProvenanceStepType.SQL
        assert prov.total_rows_accessed == 1

    def test_add_chunk_step(self):
        builder = ProvenanceBuilder()
        builder.add_chunk_step(
            chunk_ids=["doc#0", "doc#1"],
            similarity_scores=[0.9, 0.8],
        )
        prov = builder.build()
        assert prov.total_chunks_retrieved == 2

    def test_chaining(self):
        prov = (
            ProvenanceBuilder()
            .add_chunk_step(chunk_ids=["c1"])
            .add_sql_step(query="Q", tables=["t"])
            .add_llm_step(model_used="gpt-4")
            .set_classification(QueryType.HYBRID)
            .build()
        )
        assert len(prov.steps) == 3
        assert prov.query_classification == QueryType.HYBRID

    def test_get_all_tables(self):
        builder = ProvenanceBuilder()
        builder.add_sql_step(query="Q1", tables=["a", "b"])
        builder.add_spatial_step(query="Q2", tables=["b", "c"])
        assert set(builder.get_all_tables()) == {"a", "b", "c"}


class TestAttributionMetrics:
    def test_extract_entities_from_text(self):
        metrics = AttributionMetrics()
        entities = metrics.extract_entities_from_text("Asset T-4421 was deployed at pole_123")
        assert "T-4421" in entities or "4421" in entities

    def test_compute_attribution_full_coverage(self):
        metrics = AttributionMetrics()
        prov = Provenance(
            steps=[
                ProvenanceStep(
                    type=ProvenanceStepType.TEXT_CHUNK,
                    chunk_ids=["doc_17#section_2"],
                )
            ]
        )
        report = metrics.compute_attribution("Chunk doc_17#section_2 says...", prov)
        assert isinstance(report, AttributionReport)

    def test_no_hallucination_when_no_entities(self):
        metrics = AttributionMetrics()
        prov = Provenance()
        report = metrics.compute_attribution("This is a plain answer.", prov)
        assert report.coverage_score == 1.0  # No entities to be unsupported

    def test_batch_analysis(self):
        metrics = AttributionMetrics()
        prov = Provenance()
        results = metrics.batch_attribution_analysis([("answer", prov)])
        assert results["num_samples"] == 1
        assert "hallucination_rate" in results
