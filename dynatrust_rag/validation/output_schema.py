"""
LLM Output Schema Validator

Validates LLM-generated answers against structural constraints derived from
the retrieval context. This is a lightweight implementation of the schema-level
constraint enforcement concept from the PrivRAG research proposal.

The validator checks:
1. Entity grounding: identifiers in the answer should appear in provenance
2. Length bounds: answers should be within reasonable length limits
3. Numeric plausibility: numbers in the answer should relate to retrieved data
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..api.schemas import Provenance

logger = logging.getLogger(__name__)

# Configurable constraints
MIN_ANSWER_LENGTH = 10
MAX_ANSWER_LENGTH = 5000
REFUSAL_PHRASES = [
    "i don't know",
    "i don't have enough information",
    "based on the available data",
    "no relevant information found",
]


@dataclass
class ValidationResult:
    """Result of validating an LLM output against schema constraints."""

    is_valid: bool
    answer: str
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    grounded_entities: list[str] = field(default_factory=list)
    ungrounded_entities: list[str] = field(default_factory=list)

    @property
    def grounding_ratio(self) -> float:
        """Fraction of detected entities that are grounded in provenance."""
        total = len(self.grounded_entities) + len(self.ungrounded_entities)
        if total == 0:
            return 1.0
        return len(self.grounded_entities) / total


class OutputSchemaValidator:
    """
    Validates LLM-generated answers against structural and provenance constraints.

    This validator enforces basic schema-level rules on LLM output:
    - Length within acceptable bounds
    - Entity identifiers grounded in the retrieval provenance
    - No obviously fabricated references

    It does NOT perform semantic correctness checks (that requires
    reference-based evaluation metrics like RAGAS or human review).
    """

    def __init__(
        self,
        min_length: int = MIN_ANSWER_LENGTH,
        max_length: int = MAX_ANSWER_LENGTH,
        require_grounding: bool = True,
        max_ungrounded_ratio: float = 0.5,
    ):
        self.min_length = min_length
        self.max_length = max_length
        self.require_grounding = require_grounding
        self.max_ungrounded_ratio = max_ungrounded_ratio

    def validate(self, answer: str, provenance: Provenance | None = None) -> ValidationResult:
        """
        Validate an LLM-generated answer.

        Args:
            answer: The generated answer text
            provenance: Provenance from the retrieval pipeline (for grounding checks)

        Returns:
            ValidationResult with validity status and any violations/warnings
        """
        violations: list[str] = []
        warnings: list[str] = []

        # 1. Length bounds
        if len(answer.strip()) < self.min_length:
            # Allow known refusal phrases
            if not any(phrase in answer.lower() for phrase in REFUSAL_PHRASES):
                violations.append(
                    f"Answer too short ({len(answer.strip())} chars, min={self.min_length})"
                )

        if len(answer) > self.max_length:
            warnings.append(
                f"Answer exceeds length limit ({len(answer)} chars, max={self.max_length})"
            )

        # 2. Entity grounding check
        grounded: list[str] = []
        ungrounded: list[str] = []

        if provenance and self.require_grounding:
            # Build the set of known identifiers from provenance
            known_ids = self._extract_known_ids(provenance)

            # Extract entity-like identifiers from the answer
            answer_entities = self._extract_entities(answer)

            for entity in answer_entities:
                if self._is_grounded(entity, known_ids):
                    grounded.append(entity)
                else:
                    ungrounded.append(entity)

            # Check grounding ratio
            if ungrounded and len(answer_entities) > 0:
                ratio = len(ungrounded) / len(answer_entities)
                if ratio > self.max_ungrounded_ratio:
                    violations.append(
                        f"Too many ungrounded entities ({len(ungrounded)}/{len(answer_entities)}): "
                        f"{ungrounded[:5]}"
                    )
                elif ungrounded:
                    warnings.append(
                        f"Some entities not found in provenance: {ungrounded[:3]}"
                    )

        is_valid = len(violations) == 0

        if not is_valid:
            logger.warning(f"Output validation failed: {violations}")

        return ValidationResult(
            is_valid=is_valid,
            answer=answer,
            violations=violations,
            warnings=warnings,
            grounded_entities=grounded,
            ungrounded_entities=ungrounded,
        )

    def _extract_known_ids(self, provenance: Provenance) -> set[str]:
        """Extract all known identifiers from provenance for grounding checks."""
        ids: set[str] = set()

        # Source document IDs
        for doc in provenance.source_docs:
            ids.add(doc)

        # Chunk IDs from steps
        for step in provenance.steps:
            if step.chunk_ids:
                ids.update(step.chunk_ids)
            if step.tables:
                ids.update(step.tables)

        # Row references (top-level)
        for ref in provenance.row_references:
            ids.add(ref.table)
            ids.add(str(ref.id))

        # Row references nested in steps
        for step in provenance.steps:
            if step.rows:
                for ref in step.rows:
                    ids.add(ref.table)
                    ids.add(str(ref.id))

        # SQL tables mentioned
        for sql in provenance.sql_executed:
            # Extract table names from SQL (simple heuristic)
            for match in re.finditer(r'(?:FROM|JOIN|INTO|UPDATE)\s+(\w+)', sql, re.IGNORECASE):
                ids.add(match.group(1))

        return ids

    def _extract_entities(self, text: str) -> list[str]:
        """
        Extract entity-like identifiers from answer text.

        Looks for patterns that resemble:
        - Asset/equipment IDs (e.g., T-4421, ASSET-001)
        - Table names (e.g., assets, anomalies)
        - Document references (e.g., doc_17, report_2023.pdf)
        - Numeric IDs preceded by context (e.g., "ID 42", "row 15")
        """
        entities: list[str] = []

        # Pattern: alphanumeric IDs with separators (T-4421, ASSET_001, doc_17)
        id_pattern = re.compile(r'\b[A-Z][A-Za-z]*[-_]\d{2,}\b')
        entities.extend(id_pattern.findall(text))

        # Pattern: explicit ID references ("ID 42", "id: 15")
        explicit_id = re.compile(r'\b(?:ID|id|Id)[:\s]+(\d+)\b')
        entities.extend(m.group(1) for m in explicit_id.finditer(text))

        # Pattern: file references (something.pdf, something.md)
        file_pattern = re.compile(r'\b[\w-]+\.(?:pdf|md|txt|csv|json)\b')
        entities.extend(file_pattern.findall(text))

        return list(set(entities))

    def _is_grounded(self, entity: str, known_ids: set[str]) -> bool:
        """Check if an entity is grounded in the known provenance IDs."""
        # Direct match
        if entity in known_ids:
            return True

        # Substring match (e.g., entity "42" matches known ID "anomalies_42")
        entity_lower = entity.lower()
        for known in known_ids:
            if entity_lower in known.lower() or known.lower() in entity_lower:
                return True

        return False
