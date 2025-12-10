"""
DynaTrust-RAG Attribution Metrics

Helper functions for computing attribution quality metrics.
These are designed for future evaluation experiments.

Metrics to support:
- Coverage: What fraction of claims in the answer have supporting evidence?
- Precision: What fraction of retrieved evidence is actually used?
- Hallucination detection: Are there entity IDs in the answer not in evidence?
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from ..api.schemas import Provenance


@dataclass
class AttributionReport:
    """
    Report on attribution quality for a single answer.
    
    Attributes:
        entities_in_answer: Entity IDs mentioned in the answer
        entities_in_evidence: Entity IDs present in provenance
        supported_entities: Entities that appear in both
        unsupported_entities: Entities in answer but not in evidence
        coverage_score: Fraction of answer entities that are supported
        evidence_utilization: Fraction of evidence entities used in answer
    """
    entities_in_answer: Set[str]
    entities_in_evidence: Set[str]
    supported_entities: Set[str]
    unsupported_entities: Set[str]
    coverage_score: float
    evidence_utilization: float
    
    def has_potential_hallucination(self) -> bool:
        """Check if there are unsupported entities (potential hallucinations)."""
        return len(self.unsupported_entities) > 0


class AttributionMetrics:
    """
    Compute attribution quality metrics for answers.
    
    This class provides tools for evaluating whether answers
    are properly grounded in the retrieved evidence.
    """
    
    # Patterns for extracting entity-like references from text
    ENTITY_PATTERNS = [
        r'\b[A-Z]-\d{3,}\b',  # e.g., T-4421, A-123
        r'\b[a-z]+_\d+\b',     # e.g., transformer_42, pole_123
        r'\bid[:\s]+(\d+)\b',  # e.g., id: 42, id 123
        r'\b[A-Z]{2,3}\d{3,}\b',  # e.g., OBS123, ANM456
    ]
    
    def __init__(self):
        """Initialize the metrics calculator."""
        self._compiled_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.ENTITY_PATTERNS
        ]
    
    def extract_entities_from_text(self, text: str) -> Set[str]:
        """
        Extract entity-like identifiers from text.
        
        Args:
            text: Text to search for entity references
            
        Returns:
            Set of extracted entity identifiers
        """
        entities = set()
        for pattern in self._compiled_patterns:
            matches = pattern.findall(text)
            entities.update(matches)
        return entities
    
    def extract_entities_from_provenance(self, provenance: Provenance) -> Set[str]:
        """
        Extract all entity IDs from provenance.
        
        Args:
            provenance: Provenance object to analyze
            
        Returns:
            Set of entity identifiers from evidence
        """
        entities = set()
        
        for step in provenance.steps:
            # Extract from row references
            if step.rows:
                for row in step.rows:
                    entities.add(str(row.id))
            
            # Extract from chunk IDs
            if step.chunk_ids:
                for chunk_id in step.chunk_ids:
                    # Chunk IDs are like "doc_17#section_2"
                    entities.add(chunk_id)
        
        return entities
    
    def compute_attribution(
        self,
        answer: str,
        provenance: Provenance,
    ) -> AttributionReport:
        """
        Compute attribution metrics for an answer.
        
        Args:
            answer: The generated answer text
            provenance: The provenance record
            
        Returns:
            AttributionReport with computed metrics
        """
        entities_in_answer = self.extract_entities_from_text(answer)
        entities_in_evidence = self.extract_entities_from_provenance(provenance)
        
        supported = entities_in_answer & entities_in_evidence
        unsupported = entities_in_answer - entities_in_evidence
        
        coverage = (
            len(supported) / len(entities_in_answer)
            if entities_in_answer else 1.0
        )
        
        utilization = (
            len(supported) / len(entities_in_evidence)
            if entities_in_evidence else 0.0
        )
        
        return AttributionReport(
            entities_in_answer=entities_in_answer,
            entities_in_evidence=entities_in_evidence,
            supported_entities=supported,
            unsupported_entities=unsupported,
            coverage_score=coverage,
            evidence_utilization=utilization,
        )
    
    def batch_attribution_analysis(
        self,
        answers_and_provenance: List[Tuple[str, Provenance]],
    ) -> Dict[str, float]:
        """
        Compute aggregate attribution metrics over a batch.
        
        Args:
            answers_and_provenance: List of (answer, provenance) pairs
            
        Returns:
            Dictionary with aggregate metrics
        """
        if not answers_and_provenance:
            return {
                "mean_coverage": 0.0,
                "mean_utilization": 0.0,
                "hallucination_rate": 0.0,
                "num_samples": 0,
            }
        
        reports = [
            self.compute_attribution(answer, prov)
            for answer, prov in answers_and_provenance
        ]
        
        mean_coverage = sum(r.coverage_score for r in reports) / len(reports)
        mean_utilization = sum(r.evidence_utilization for r in reports) / len(reports)
        hallucination_rate = sum(
            1 for r in reports if r.has_potential_hallucination()
        ) / len(reports)
        
        return {
            "mean_coverage": mean_coverage,
            "mean_utilization": mean_utilization,
            "hallucination_rate": hallucination_rate,
            "num_samples": len(reports),
        }
