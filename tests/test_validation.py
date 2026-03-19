"""Tests for LLM output schema validation."""

from dynatrust_rag.api.schemas import (
    Provenance,
    ProvenanceStep,
    ProvenanceStepType,
)
from dynatrust_rag.validation import OutputSchemaValidator, ValidationResult


class TestOutputSchemaValidator:
    def test_valid_answer(self):
        validator = OutputSchemaValidator()
        result = validator.validate("This is a valid answer with enough content.")
        assert result.is_valid is True
        assert result.violations == []

    def test_too_short_answer(self):
        validator = OutputSchemaValidator(min_length=20)
        result = validator.validate("Short.")
        assert result.is_valid is False
        assert any("too short" in v.lower() for v in result.violations)

    def test_refusal_is_valid_even_if_short(self):
        validator = OutputSchemaValidator(min_length=50)
        result = validator.validate("I don't know based on the available data.")
        assert result.is_valid is True

    def test_long_answer_warning(self):
        validator = OutputSchemaValidator(max_length=50)
        result = validator.validate("A" * 100)
        assert result.is_valid is True  # warning, not violation
        assert len(result.warnings) > 0

    def test_grounded_entities(self):
        validator = OutputSchemaValidator()
        prov = Provenance(
            steps=[
                ProvenanceStep(
                    type=ProvenanceStepType.TEXT_CHUNK,
                    chunk_ids=["telecom_report_2023#chunk_0"],
                )
            ],
            source_docs=["telecom_report_2023.pdf"],
        )
        result = validator.validate(
            "According to telecom_report_2023.pdf, anomalies were detected.",
            prov,
        )
        assert result.is_valid is True
        assert "telecom_report_2023.pdf" in result.grounded_entities

    def test_ungrounded_entity_warning(self):
        validator = OutputSchemaValidator(max_ungrounded_ratio=0.8)
        prov = Provenance()
        result = validator.validate(
            "Asset T-9999 was found in report_phantom.pdf near sector Z.",
            prov,
        )
        # Should have ungrounded entities
        assert len(result.ungrounded_entities) > 0

    def test_grounding_ratio(self):
        result = ValidationResult(
            is_valid=True,
            answer="test",
            grounded_entities=["a", "b", "c"],
            ungrounded_entities=["d"],
        )
        assert result.grounding_ratio == 0.75

    def test_grounding_ratio_no_entities(self):
        result = ValidationResult(is_valid=True, answer="test")
        assert result.grounding_ratio == 1.0
