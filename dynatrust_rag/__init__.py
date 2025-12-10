"""
DynaTrust-RAG: Hybrid Retrieval-Augmented Generation with Provenance and Staleness Awareness

A research prototype for answering natural-language questions over dynamic
spatial-relational PostgreSQL/PostGIS databases, featuring:

- Hybrid semantic + spatial + SQL retrieval
- Explicit attribution/provenance for every answer
- Staleness-awareness when vector indices lag behind live spatial data
- Hooks for future evaluation (accuracy, hallucination detection, robustness)

This module is designed as a distinct research system built on top of the
Atlas4D database infrastructure.

Author: Research Prototype
Version: 0.1.0
"""

__version__ = "0.1.0"
__author__ = "DynaTrust Research"

from .api.router import dynatrust_router

__all__ = ["dynatrust_router", "__version__"]
