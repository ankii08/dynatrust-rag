"""
DynaTrust-RAG Staleness Tracker

Monitors and reports on the freshness of vector indices relative
to the live spatial/relational data in PostgreSQL.

Design:
- Tracks last_vector_refresh_at in a metadata table
- Compares against max(updated_at) from source tables
- Provides staleness signals to influence retrieval strategy
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from ..api.schemas import QueryRequest, StalenessInfo
from ..config import DynaTrustConfig
from ..db.connection import get_pool


@dataclass
class IndexStatus:
    """Status of the vector index."""
    last_refresh_at: Optional[datetime]
    total_chunks: int
    is_healthy: bool
    notes: Optional[str] = None


class StalenessTracker:
    """
    Tracks staleness of vector indices relative to source data.
    
    The tracker maintains metadata about when vector embeddings
    were last refreshed and compares this against the timestamps
    of source records to detect staleness.
    
    Staleness affects retrieval strategy:
    - Low staleness: Full hybrid retrieval with semantic search
    - Medium staleness: Semantic results are down-weighted
    - High staleness: Semantic search is skipped entirely
    """
    
    # Metadata table for tracking vector refresh status
    METADATA_TABLE = "dynatrust.vector_index_metadata"
    
    # Source tables to check for updates
    SOURCE_TABLES = [
        ("atlas4d.observations_core", "t"),
        ("atlas4d.anomalies", "detected_at"),
    ]
    
    def __init__(self, config: DynaTrustConfig):
        """
        Initialize the staleness tracker.
        
        Args:
            config: DynaTrust configuration
        """
        self.config = config
        self.staleness_threshold = config.vector.staleness_threshold_seconds
    
    async def check_staleness(
        self,
        request: QueryRequest,
    ) -> StalenessInfo:
        """
        Check staleness status for a query.
        
        Compares the last vector refresh time against:
        1. The current time
        2. The most recent updates in relevant source tables
        3. Any spatial/temporal constraints in the request
        
        Args:
            request: The query request to analyze
            
        Returns:
            StalenessInfo with detailed freshness information
        """
        try:
            pool = await get_pool()
            if not pool:
                return self._default_staleness_info(
                    notes="Database not available; assuming fresh data"
                )
            
            async with pool.acquire() as conn:
                # Get last vector refresh time
                last_refresh = await self._get_last_refresh_time(conn)
                
                # Get newest relevant data timestamp
                newest_data = await self._get_newest_data_time(conn, request)
                
                # Calculate staleness
                now = datetime.now(timezone.utc)
                
                if last_refresh is None:
                    # No refresh recorded - assume very stale
                    return StalenessInfo(
                        vector_index_lag_seconds=None,
                        last_vector_refresh_at=None,
                        newest_relevant_data_at=newest_data,
                        used_semantic_results=False,
                        staleness_detected=True,
                        notes="No vector index refresh recorded; using SQL/spatial only.",
                    )
                
                # Ensure timezone awareness
                if last_refresh.tzinfo is None:
                    last_refresh = last_refresh.replace(tzinfo=timezone.utc)
                
                lag_seconds = int((now - last_refresh).total_seconds())
                
                # Check if data has been updated since last refresh
                data_is_newer = False
                if newest_data:
                    if newest_data.tzinfo is None:
                        newest_data = newest_data.replace(tzinfo=timezone.utc)
                    data_is_newer = newest_data > last_refresh
                
                # Determine staleness level
                staleness_detected = (
                    lag_seconds > self.staleness_threshold or
                    data_is_newer
                )
                
                # Decide whether to use semantic results
                use_semantic = True
                notes = None
                
                if lag_seconds > self.config.retrieval.max_staleness_for_semantic_seconds:
                    use_semantic = False
                    notes = (
                        f"Vector index is {lag_seconds}s old (>{self.config.retrieval.max_staleness_for_semantic_seconds}s threshold); "
                        "semantic search disabled."
                    )
                elif data_is_newer:
                    use_semantic = True  # Still use, but will be down-weighted
                    notes = (
                        f"Some source data updated after last vector refresh; "
                        "semantic results will be down-weighted."
                    )
                
                return StalenessInfo(
                    vector_index_lag_seconds=lag_seconds,
                    last_vector_refresh_at=last_refresh,
                    newest_relevant_data_at=newest_data,
                    used_semantic_results=use_semantic,
                    staleness_detected=staleness_detected,
                    notes=notes,
                )
                
        except Exception as e:
            return self._default_staleness_info(
                notes=f"Error checking staleness: {e}"
            )
    
    async def _get_last_refresh_time(self, conn) -> Optional[datetime]:
        """
        Get the last vector index refresh time from metadata.
        
        Args:
            conn: Database connection
            
        Returns:
            Last refresh timestamp or None
        """
        try:
            result = await conn.fetchval(f"""
                SELECT last_refresh_at 
                FROM {self.METADATA_TABLE}
                WHERE index_name = 'document_chunks'
                ORDER BY last_refresh_at DESC
                LIMIT 1
            """)
            return result
        except Exception:
            # Table might not exist yet
            return None
    
    async def _get_newest_data_time(
        self,
        conn,
        request: QueryRequest,
    ) -> Optional[datetime]:
        """
        Get the timestamp of the most recently updated relevant data.
        
        Args:
            conn: Database connection
            request: Query request for context
            
        Returns:
            Newest data timestamp or None
        """
        max_times = []
        
        for table, ts_col in self.SOURCE_TABLES:
            try:
                # Build query with optional filters
                query = f"SELECT MAX({ts_col}) FROM {table}"
                
                # Add time constraint if specified
                if request.time_window and request.time_window.last_n_hours:
                    query += f" WHERE {ts_col} >= NOW() - INTERVAL '{request.time_window.last_n_hours} hours'"
                
                result = await conn.fetchval(query)
                if result:
                    max_times.append(result)
            except Exception:
                continue
        
        return max(max_times) if max_times else None
    
    async def get_index_status(self) -> Dict:
        """
        Get overall status of the vector index.
        
        Returns:
            Dictionary with index health information
        """
        try:
            pool = await get_pool()
            if not pool:
                return {
                    "status": "unavailable",
                    "message": "Database not connected",
                }
            
            async with pool.acquire() as conn:
                last_refresh = await self._get_last_refresh_time(conn)
                
                # Try to get chunk count
                try:
                    chunk_count = await conn.fetchval(
                        "SELECT COUNT(*) FROM dynatrust.document_chunks"
                    ) or 0
                except Exception:
                    chunk_count = 0
                
                now = datetime.now(timezone.utc)
                
                if last_refresh is None:
                    return {
                        "status": "not_initialized",
                        "total_chunks": chunk_count,
                        "message": "Vector index has not been refreshed yet",
                    }
                
                if last_refresh.tzinfo is None:
                    last_refresh = last_refresh.replace(tzinfo=timezone.utc)
                
                lag = int((now - last_refresh).total_seconds())
                
                status = "healthy"
                if lag > self.config.retrieval.max_staleness_for_semantic_seconds:
                    status = "stale"
                elif lag > self.staleness_threshold:
                    status = "degraded"
                
                return {
                    "status": status,
                    "last_refresh_at": last_refresh.isoformat(),
                    "lag_seconds": lag,
                    "total_chunks": chunk_count,
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
            }
    
    async def record_refresh(self, chunk_count: int) -> bool:
        """
        Record a vector index refresh event.
        
        Called after embeddings are refreshed to update the metadata.
        
        Args:
            chunk_count: Number of chunks in the refreshed index
            
        Returns:
            True if recorded successfully
        """
        try:
            pool = await get_pool()
            if not pool:
                return False
            
            async with pool.acquire() as conn:
                await conn.execute(f"""
                    INSERT INTO {self.METADATA_TABLE} 
                    (index_name, last_refresh_at, chunk_count)
                    VALUES ('document_chunks', NOW(), $1)
                    ON CONFLICT (index_name) 
                    DO UPDATE SET 
                        last_refresh_at = NOW(),
                        chunk_count = $1
                """, chunk_count)
                return True
                
        except Exception as e:
            print(f"[StalenessTracker] Error recording refresh: {e}")
            return False
    
    def _default_staleness_info(self, notes: str) -> StalenessInfo:
        """Create a default StalenessInfo for error cases."""
        return StalenessInfo(
            vector_index_lag_seconds=None,
            last_vector_refresh_at=None,
            newest_relevant_data_at=None,
            used_semantic_results=True,  # Optimistic default
            staleness_detected=False,
            notes=notes,
        )
