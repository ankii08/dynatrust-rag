"""
DynaTrust-RAG Attribution Module

Handles provenance tracking and attribution metrics for answers.
"""

from .provenance import ProvenanceBuilder
from .metrics import AttributionMetrics

__all__ = ["ProvenanceBuilder", "AttributionMetrics"]
