"""
DynaTrust-RAG Query Logger

Logs queries and answers for evaluation purposes.
Supports future experiments on accuracy, hallucination, and robustness.

Design:
- All queries are logged to the dynatrust_queries table
- Provenance is stored for post-hoc analysis
- Gold labels can be added later for evaluation
"""

import json
from datetime import datetime
from typing import Optional

from ..api.schemas import (
    Provenance,
    QueryRequest,
    QueryResponse,
)
from ..config import DynaTrustConfig
from ..db.connection import get_pool


class QueryLogger:
    """
    Logger for DynaTrust-RAG queries and answers.
    
    Stores all query-answer pairs for:
    - Reproducibility (replay queries)
    - Evaluation (compare against gold labels)
    - Analysis (attribution quality, hallucination detection)
    """
    
    QUERIES_TABLE = "dynatrust.queries"
    ANSWERS_TABLE = "dynatrust.answers"
    GOLD_LABELS_TABLE = "dynatrust.gold_labels"
    
    def __init__(self, config: DynaTrustConfig):
        """
        Initialize the query logger.
        
        Args:
            config: DynaTrust configuration
        """
        self.config = config
        self.enabled = config.evaluation.enable_query_logging
    
    async def log_query(
        self,
        query_id: str,
        request: QueryRequest,
        response: QueryResponse,
    ) -> bool:
        """
        Log a query and its response.
        
        Args:
            query_id: Unique query identifier
            request: The original query request
            response: The generated response
            
        Returns:
            True if logged successfully
        """
        if not self.enabled:
            return True
        
        try:
            pool = await get_pool()
            if not pool:
                return False
            
            async with pool.acquire() as conn:
                # Log the query
                await conn.execute(f"""
                    INSERT INTO {self.QUERIES_TABLE}
                    (query_id, question, request_json, session_id, created_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (query_id) DO UPDATE SET
                        question = EXCLUDED.question,
                        request_json = EXCLUDED.request_json
                """,
                    query_id,
                    request.question,
                    json.dumps(request.model_dump(), default=str),
                    request.session_id,
                    datetime.utcnow(),
                )
                
                # Log the answer
                provenance_json = None
                if response.provenance:
                    provenance_json = json.dumps(
                        response.provenance.model_dump(), 
                        default=str
                    )
                
                staleness_json = None
                if response.staleness_info:
                    staleness_json = json.dumps(
                        response.staleness_info.model_dump(),
                        default=str
                    )
                
                await conn.execute(f"""
                    INSERT INTO {self.ANSWERS_TABLE}
                    (query_id, answer, provenance_json, staleness_json, 
                     query_type, processing_time_ms, confidence_score, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (query_id) DO UPDATE SET
                        answer = EXCLUDED.answer,
                        provenance_json = EXCLUDED.provenance_json,
                        staleness_json = EXCLUDED.staleness_json,
                        processing_time_ms = EXCLUDED.processing_time_ms
                """,
                    query_id,
                    response.answer,
                    provenance_json,
                    staleness_json,
                    response.query_type.value,
                    response.processing_time_ms,
                    response.confidence_score,
                    datetime.utcnow(),
                )
                
                return True
                
        except Exception as e:
            print(f"[QueryLogger] Error logging query {query_id}: {e}")
            return False
    
    async def get_provenance(self, query_id: str) -> Optional[Provenance]:
        """
        Retrieve provenance for a previous query.
        
        Args:
            query_id: The query identifier
            
        Returns:
            Provenance object or None if not found
        """
        try:
            pool = await get_pool()
            if not pool:
                return None
            
            async with pool.acquire() as conn:
                row = await conn.fetchrow(f"""
                    SELECT provenance_json 
                    FROM {self.ANSWERS_TABLE}
                    WHERE query_id = $1
                """, query_id)
                
                if row and row['provenance_json']:
                    data = json.loads(row['provenance_json'])
                    return Provenance(**data)
                
                return None
                
        except Exception as e:
            print(f"[QueryLogger] Error retrieving provenance for {query_id}: {e}")
            return None
    
    async def add_gold_label(
        self,
        query_id: str,
        gold_answer: str,
        rating: Optional[int] = None,
        notes: Optional[str] = None,
        annotator: Optional[str] = None,
    ) -> bool:
        """
        Add a gold label for a query.
        
        Used for evaluation experiments.
        
        Args:
            query_id: The query identifier
            gold_answer: The correct/expected answer
            rating: Optional quality rating (1-5)
            notes: Optional annotator notes
            annotator: Identifier of the person/system adding the label
            
        Returns:
            True if added successfully
        """
        try:
            pool = await get_pool()
            if not pool:
                return False
            
            async with pool.acquire() as conn:
                await conn.execute(f"""
                    INSERT INTO {self.GOLD_LABELS_TABLE}
                    (query_id, gold_answer, rating, notes, annotator, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (query_id) DO UPDATE SET
                        gold_answer = EXCLUDED.gold_answer,
                        rating = EXCLUDED.rating,
                        notes = EXCLUDED.notes,
                        annotator = EXCLUDED.annotator
                """,
                    query_id,
                    gold_answer,
                    rating,
                    notes,
                    annotator,
                    datetime.utcnow(),
                )
                return True
                
        except Exception as e:
            print(f"[QueryLogger] Error adding gold label for {query_id}: {e}")
            return False
    
    async def get_evaluation_batch(
        self,
        limit: int = 100,
        with_gold_labels: bool = True,
    ) -> list:
        """
        Get a batch of queries for evaluation.
        
        Args:
            limit: Maximum number of queries to return
            with_gold_labels: If True, only return queries with gold labels
            
        Returns:
            List of query-answer-label tuples
        """
        try:
            pool = await get_pool()
            if not pool:
                return []
            
            async with pool.acquire() as conn:
                if with_gold_labels:
                    query = f"""
                        SELECT 
                            q.query_id,
                            q.question,
                            a.answer,
                            a.provenance_json,
                            g.gold_answer,
                            g.rating
                        FROM {self.QUERIES_TABLE} q
                        JOIN {self.ANSWERS_TABLE} a ON q.query_id = a.query_id
                        JOIN {self.GOLD_LABELS_TABLE} g ON q.query_id = g.query_id
                        ORDER BY q.created_at DESC
                        LIMIT $1
                    """
                else:
                    query = f"""
                        SELECT 
                            q.query_id,
                            q.question,
                            a.answer,
                            a.provenance_json,
                            NULL as gold_answer,
                            NULL as rating
                        FROM {self.QUERIES_TABLE} q
                        JOIN {self.ANSWERS_TABLE} a ON q.query_id = a.query_id
                        ORDER BY q.created_at DESC
                        LIMIT $1
                    """
                
                rows = await conn.fetch(query, limit)
                return [dict(row) for row in rows]
                
        except Exception as e:
            print(f"[QueryLogger] Error getting evaluation batch: {e}")
            return []
