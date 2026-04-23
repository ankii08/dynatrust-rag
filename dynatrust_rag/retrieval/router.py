"""
DynaTrust-RAG Query Router

Classifies incoming natural language queries and routes them to the
appropriate retrieval strategy (or combination for hybrid queries).

How it works:
1. Analyzes the QueryRequest to determine query type
2. Routes to appropriate retrievers (semantic, spatial, structured, or hybrid)
3. Merges results from multiple retrievers
4. Returns unified RetrievalResult with all data and provenance

Query classification logic:
- SPATIAL: QueryRequest.spatial is set OR keywords like "near", "within", "around"
- STRUCTURED: Contains year patterns ("after 2020") or attribute keywords
- SEMANTIC: Contains natural language requiring embedding search
- HYBRID: Multiple signals present (most common)

Design:
- Lazy initialization of retrievers
- Configurable via DynaTrustConfig
- Merges results with proper metadata
"""

import re
from dataclasses import dataclass
from typing import List, Optional

from ..api.schemas import QueryRequest, QueryType
from .base import RetrievalResult
from .semantic import SemanticRetriever
from .spatial import SpatialRetriever
from .structured import StructuredRetriever


# =============================================================================
# Query Classification
# =============================================================================

@dataclass
class QueryClassification:
    """
    Result of analyzing a query to determine retrieval strategy.
    
    Attributes:
        query_type: Overall classification (TEXT_ONLY, SPATIAL, STRUCTURED, HYBRID)
        use_semantic: Whether to run semantic retrieval
        use_spatial: Whether to run spatial retrieval
        use_structured: Whether to run structured retrieval
        confidence: Confidence in the classification (0-1)
        signals: List of signals that contributed to classification
    """
    query_type: QueryType
    use_semantic: bool
    use_spatial: bool
    use_structured: bool
    confidence: float
    signals: List[str]


class QueryClassifier:
    """
    Classifies queries to determine which retrievers to use.
    
    Uses keyword patterns and explicit constraints from QueryRequest
    to determine the optimal retrieval strategy.
    """
    
    # Keywords indicating spatial intent
    SPATIAL_KEYWORDS = {
        "near", "within", "around", "nearby",
        "meters", "meter", "kilometres", "kilometers", "km", "miles",
        "location", "area", "region", "zone", "port", "city",
        "latitude", "longitude", "coordinates", "radius",
    }
    SPATIAL_PHRASES = {"close to", "next to", "radius of"}
    
    # Keywords indicating structured/SQL intent  
    STRUCTURED_KEYWORDS = {
        "after", "before", "since", "until", "between",
        "status", "type", "severity", "count",
        "installed", "created", "active", "inactive", "decommissioned",
    }
    STRUCTURED_PHRASES = {"how many", "list all", "show all"}
    
    # Patterns for years
    YEAR_PATTERN = re.compile(r'\b(?:19|20)\d{2}\b')

    @staticmethod
    def _tokenize_question(question: str) -> set[str]:
        """Tokenize the question into normalized word-like units."""
        return set(re.findall(r"\b[\w-]+\b", question.lower()))
    
    def classify(self, query: QueryRequest) -> QueryClassification:
        """
        Classify a query to determine retrieval strategy.
        
        Args:
            query: The QueryRequest to classify
            
        Returns:
            QueryClassification with retrieval decisions
        """
        signals: List[str] = []
        question_lower = query.question.lower()
        question_words = self._tokenize_question(query.question)
        
        # Check for explicit spatial constraint
        has_spatial_constraint = query.spatial is not None
        if has_spatial_constraint:
            signals.append("explicit_spatial_constraint")
        
        # Check for spatial keywords
        spatial_keywords_found = self.SPATIAL_KEYWORDS & question_words
        if spatial_keywords_found:
            signals.append(f"spatial_keywords: {spatial_keywords_found}")

        # Check for spatial phrases (multi-word)
        spatial_phrases_found = []
        for phrase in self.SPATIAL_PHRASES:
            if phrase in question_lower:
                signals.append(f"spatial_phrase: {phrase}")
                spatial_phrases_found.append(phrase)

        # Check for structured keywords
        structured_keywords_found = self.STRUCTURED_KEYWORDS & question_words
        if structured_keywords_found:
            signals.append(f"structured_keywords: {structured_keywords_found}")

        structured_phrases_found = []
        for phrase in self.STRUCTURED_PHRASES:
            if phrase in question_lower:
                signals.append(f"structured_phrase: {phrase}")
                structured_phrases_found.append(phrase)
        
        # Check for year patterns
        years = self.YEAR_PATTERN.findall(question_lower)
        if years:
            signals.append(f"year_references: {years}")
        
        # Check for time window constraint
        if query.time_window:
            signals.append("explicit_time_window")
        
        # Check for source type filter
        if query.source_types:
            signals.append(f"source_types_filter: {query.source_types}")
        
        # Determine retriever usage
        use_spatial = (
            has_spatial_constraint
            or bool(spatial_keywords_found)
            or bool(spatial_phrases_found)
        )
        use_structured = (
            bool(structured_keywords_found)
            or bool(structured_phrases_found)
            or bool(years)
            or query.time_window is not None
        )
        
        # Semantic is always useful unless forced off
        use_semantic = not query.force_live_data_only
        
        # If no clear signals, default to semantic
        if not signals:
            signals.append("no_specific_signals_default_semantic")
        
        # Determine query type
        if use_spatial and use_structured:
            query_type = QueryType.HYBRID
        elif use_spatial:
            query_type = QueryType.SPATIAL
        elif use_structured:
            query_type = QueryType.STRUCTURED
        else:
            query_type = QueryType.TEXT_ONLY
        
        # If we have both semantic and structured/spatial, it's hybrid
        if use_semantic and (use_spatial or use_structured):
            query_type = QueryType.HYBRID
        
        # Calculate confidence based on signal strength
        confidence = min(1.0, 0.5 + len(signals) * 0.1)
        
        return QueryClassification(
            query_type=query_type,
            use_semantic=use_semantic,
            use_spatial=use_spatial,
            use_structured=use_structured,
            confidence=confidence,
            signals=signals,
        )


# =============================================================================
# Hybrid Retrieval Router
# =============================================================================

class HybridRetrievalRouter:
    """
    Routes queries to appropriate retrievers and merges results.
    
    Coordinates between semantic, spatial, and structured retrievers
    based on query classification.
    
    Usage:
        router = HybridRetrievalRouter()
        result = await router.retrieve(query_request)
    """
    
    def __init__(self, pool=None):
        """
        Initialize the router with retrievers.
        
        Args:
            pool: Optional asyncpg connection pool to share
        """
        self.classifier = QueryClassifier()
        self.semantic = SemanticRetriever(pool=pool)
        self.spatial = SpatialRetriever(pool=pool)
        self.structured = StructuredRetriever(pool=pool)
    
    async def retrieve(
        self,
        query: QueryRequest,
        limit: int = 20,
    ) -> RetrievalResult:
        """
        Execute hybrid retrieval based on query classification.
        
        Runs the appropriate combination of retrievers and merges
        results into a single RetrievalResult.
        
        Args:
            query: The QueryRequest to process
            limit: Maximum total results (divided among retrievers)
            
        Returns:
            RetrievalResult with merged results from all used retrievers
        """
        # Classify the query
        classification = self.classifier.classify(query)
        
        # Track which retrievers we use
        retrievers_used: List[str] = []
        results: List[RetrievalResult] = []
        sql_by_retriever: dict[str, List[str]] = {}
        
        # Allocate limits based on how many retrievers we'll use
        num_retrievers = sum([
            classification.use_semantic,
            classification.use_spatial,
            classification.use_structured,
        ])
        per_retriever_limit = max(5, limit // max(1, num_retrievers))
        
        # Run semantic retrieval
        if classification.use_semantic:
            semantic_result = await self.semantic.retrieve(query, limit=per_retriever_limit)
            results.append(semantic_result)
            retrievers_used.append("semantic")
            sql_by_retriever["semantic"] = list(semantic_result.executed_sql)
        
        # Run spatial retrieval
        if classification.use_spatial:
            spatial_result = await self.spatial.retrieve(query, limit=per_retriever_limit)
            results.append(spatial_result)
            retrievers_used.append("spatial")
            sql_by_retriever["spatial"] = list(spatial_result.executed_sql)
        
        # Run structured retrieval
        if classification.use_structured:
            structured_result = await self.structured.retrieve(query, limit=per_retriever_limit)
            results.append(structured_result)
            retrievers_used.append("structured")
            sql_by_retriever["structured"] = list(structured_result.executed_sql)
        
        # Merge all results
        if not results:
            return RetrievalResult(
                metadata={
                    "query_type": classification.query_type.value,
                    "retrievers_used": [],
                    "classification_signals": classification.signals,
                    "note": "No retrievers executed",
                }
            )
        
        merged = results[0]
        for result in results[1:]:
            merged = merged.merge(result)
        
        # Add classification metadata
        merged.metadata["query_type"] = classification.query_type.value
        merged.metadata["retrievers_used"] = retrievers_used
        merged.metadata["classification_signals"] = classification.signals
        merged.metadata["classification_confidence"] = classification.confidence
        merged.metadata["sql_by_retriever"] = sql_by_retriever

        return merged
    
    async def health_check(self) -> dict:
        """
        Check health of all retrievers.
        
        Returns:
            Dict with health status of each retriever
        """
        return {
            "semantic": await self.semantic.health_check(),
            "spatial": await self.spatial.health_check(),
            "structured": await self.structured.health_check(),
        }


# =============================================================================
# Module-level convenience function
# =============================================================================

# Global router instance (lazy initialization)
_router: Optional[HybridRetrievalRouter] = None


async def hybrid_retrieve(query: QueryRequest, limit: int = 20) -> RetrievalResult:
    """
    Execute hybrid retrieval for a query.
    
    This is the main entry point for the retrieval system.
    Creates a router if needed and runs the retrieval.
    
    Args:
        query: The QueryRequest to process
        limit: Maximum total results
        
    Returns:
        RetrievalResult with merged results from all applicable retrievers
        
    Example:
        from dynatrust_rag.retrieval.router import hybrid_retrieve
        
        result = await hybrid_retrieve(QueryRequest(
            question="What happened near the port after 2022?",
            spatial=SpatialConstraint(latitude=42.48, longitude=27.48, radius_meters=5000)
        ))
        
        print(f"Retrieved {result.total_results} results")
        print(f"SQL executed: {result.executed_sql}")
    """
    global _router
    
    if _router is None:
        _router = HybridRetrievalRouter()
    
    return await _router.retrieve(query, limit=limit)


def get_router() -> HybridRetrievalRouter:
    """
    Get the global router instance.
    
    Returns:
        The HybridRetrievalRouter singleton
    """
    global _router
    
    if _router is None:
        _router = HybridRetrievalRouter()
    
    return _router
