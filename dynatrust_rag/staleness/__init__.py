"""
DynaTrust-RAG Staleness Module

Tracks and manages staleness of vector indices relative to live data.
"""

from .tracker import StalenessTracker

__all__ = ["StalenessTracker"]
