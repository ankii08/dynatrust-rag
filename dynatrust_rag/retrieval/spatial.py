"""
DynaTrust-RAG Spatial Retriever

Implements spatial search using PostGIS for geographic queries over
spatial data in PostgreSQL.

How it works:
1. Uses spatial constraints from QueryRequest (latitude, longitude, radius_meters)
2. Runs PostGIS queries with ST_DWithin for point-radius search
3. Returns SpatialRow objects with distance and geometry (WKT)
4. Logs executed SQL for provenance

Supported tables:
- atlas4d.observations_core (primary spatial table from Atlas4D)
- Can be extended to additional tables (transformers, parcels, etc.)

PostGIS functions used:
- ST_DWithin: Spatial filtering within radius
- ST_Distance: Calculate actual distance  
- ST_AsText: Convert geometry to WKT for provenance
- ST_SetSRID + ST_MakePoint: Create query point
"""

from typing import Any, Dict, List, Optional, Tuple

from ..api.schemas import QueryRequest
from ..db.connection import get_connection
from .base import BaseRetriever, RetrievalResult, SpatialRow


# Default search radius in meters
DEFAULT_RADIUS_METERS = 1000.0

# Default limit
DEFAULT_LIMIT = 100


class SpatialRetriever(BaseRetriever):
    """
    Spatial retriever using PostGIS for geographic queries.
    
    Supports point-radius queries using ST_DWithin against spatial tables.
    Returns rows with distance from query point and geometry as WKT.
    
    Features:
    - Configurable radius and result limit
    - Time window filtering (if QueryRequest has time_window)
    - Source type filtering
    - Provenance tracking with full SQL queries
    - Distance-based scoring (closer = higher score)
    
    Spatial tables queried:
    - atlas4d.observations_core: Main observation data with geom column
    
    Example usage:
        retriever = SpatialRetriever()
        query = QueryRequest(
            question="What happened near the port?",
            spatial=SpatialConstraint(latitude=42.48, longitude=27.48, radius_meters=5000)
        )
        result = await retriever.retrieve(query, limit=50)
        for row in result.spatial_rows:
            print(f"{row.table_name}:{row.primary_key} - {row.distance_meters}m away")
    """
    
    # Tables with spatial columns to query
    # Format: (schema.table, geom_column, id_column, timestamp_column)
    SPATIAL_TABLES: List[Tuple[str, str, str, Optional[str]]] = [
        ("dynatrust.spatial_points", "geom", "id", "created_at"),
    ]
    
    def __init__(
        self,
        pool=None,
        default_radius: float = DEFAULT_RADIUS_METERS,
        default_limit: int = DEFAULT_LIMIT,
    ):
        """
        Initialize the spatial retriever.
        
        Args:
            pool: Optional asyncpg connection pool
            default_radius: Default search radius in meters
            default_limit: Default maximum results per table
        """
        super().__init__(pool)
        self.default_radius = default_radius
        self.default_limit = default_limit
    
    async def retrieve(self, query: QueryRequest, limit: int = 100) -> RetrievalResult:
        """
        Retrieve spatially relevant records within radius of a point.
        
        Args:
            query: QueryRequest with spatial constraint (required for results)
            limit: Maximum results to return across all tables
            
        Returns:
            RetrievalResult with spatial_rows populated and executed_sql logged
        """
        # Check for spatial constraint
        if query.spatial is None:
            return RetrievalResult(
                spatial_rows=[],
                executed_sql=[],
                metadata={
                    "retrievers_used": ["spatial"],
                    "note": "No spatial constraint provided - skipped spatial retrieval",
                },
            )
        
        lat = query.spatial.latitude
        lon = query.spatial.longitude
        radius = query.spatial.radius_meters
        
        all_rows: List[SpatialRow] = []
        all_sql: List[str] = []
        
        # Calculate per-table limit
        per_table_limit = max(10, limit // len(self.SPATIAL_TABLES))
        
        for table_name, geom_col, id_col, ts_col in self.SPATIAL_TABLES:
            rows, sql = await self._query_spatial_table(
                table_name=table_name,
                geom_col=geom_col,
                id_col=id_col,
                ts_col=ts_col,
                lat=lat,
                lon=lon,
                radius_meters=radius,
                query=query,
                limit=per_table_limit,
            )
            all_rows.extend(rows)
            all_sql.append(sql)
        
        # Sort by score (distance) and limit
        all_rows.sort(key=lambda r: r.score, reverse=True)
        all_rows = all_rows[:limit]
        
        return RetrievalResult(
            spatial_rows=all_rows,
            executed_sql=all_sql,
            metadata={
                "retrievers_used": ["spatial"],
                "rows_retrieved": len(all_rows),
                "search_center": {"lat": lat, "lon": lon},
                "search_radius_meters": radius,
            },
        )
    
    async def _query_spatial_table(
        self,
        table_name: str,
        geom_col: str,
        id_col: str,
        ts_col: Optional[str],
        lat: float,
        lon: float,
        radius_meters: float,
        query: QueryRequest,
        limit: int,
    ) -> Tuple[List[SpatialRow], str]:
        """
        Query a single spatial table with ST_DWithin.
        
        Args:
            table_name: Full table name (schema.table)
            geom_col: Name of geometry column
            id_col: Name of primary key column
            ts_col: Name of timestamp column (optional)
            lat, lon: Query point coordinates
            radius_meters: Search radius
            query: Original QueryRequest for additional filters
            limit: Maximum rows to return
            
        Returns:
            Tuple of (list of SpatialRow, SQL string for provenance)
        """
        # Build the SQL query
        # Using geography for accurate distance calculation
        where_clauses = [
            f"""ST_DWithin(
                {geom_col}::geography,
                ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography,
                $3
            )"""
        ]
        params = [lon, lat, radius_meters]
        param_idx = 4
        
        # Time window filter
        if ts_col and query.time_window:
            if query.time_window.last_n_hours:
                where_clauses.append(f"{ts_col} >= NOW() - INTERVAL '{query.time_window.last_n_hours} hours'")
            elif query.time_window.start:
                where_clauses.append(f"{ts_col} >= ${param_idx}")
                params.append(query.time_window.start)
                param_idx += 1
            if query.time_window.end:
                where_clauses.append(f"{ts_col} <= ${param_idx}")
                params.append(query.time_window.end)
                param_idx += 1
        
        # Source type filter
        if query.source_types:
            where_clauses.append(f"source_type = ANY(${param_idx})")
            params.append(query.source_types)
            param_idx += 1
        
        where_sql = " AND ".join(where_clauses)
        
        sql = f"""
            SELECT 
                {id_col} AS id,
                ST_AsText({geom_col}) AS wkt,
                ST_Distance(
                    {geom_col}::geography,
                    ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography
                ) AS distance_meters,
                *
            FROM {table_name}
            WHERE {where_sql}
            ORDER BY distance_meters ASC
            LIMIT ${param_idx}
        """
        params.append(limit)
        
        # Build SQL for provenance (with actual values substituted for readability)
        sql_for_provenance = f"""
            SELECT {id_col} AS id, ST_AsText({geom_col}) AS wkt,
                   ST_Distance({geom_col}::geography, 
                   ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)::geography) AS distance_meters, *
            FROM {table_name}
            WHERE ST_DWithin({geom_col}::geography, 
                  ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)::geography, {radius_meters})
            ORDER BY distance_meters LIMIT {limit}
        """
        
        rows: List[SpatialRow] = []
        
        try:
            async with get_connection() as conn:
                records = await conn.fetch(sql, *params)
                
                for record in records:
                    distance = float(record["distance_meters"])
                    
                    # Convert to score (closer = higher)
                    score = self.distance_to_score(distance, max_distance=radius_meters)
                    
                    # Build data dict (excluding special columns)
                    data = {}
                    for key, value in record.items():
                        if key not in ("id", "wkt", "distance_meters", geom_col):
                            # Handle special types
                            if hasattr(value, "isoformat"):
                                data[key] = value.isoformat()
                            elif isinstance(value, (dict, list)):
                                data[key] = value
                            else:
                                data[key] = value
                    
                    row = SpatialRow(
                        table_name=table_name.split(".")[-1],  # Just table name
                        primary_key=record["id"],
                        wkt_geometry=record["wkt"],
                        distance_meters=distance,
                        data=data,
                        score=score,
                    )
                    rows.append(row)
                    
        except Exception as e:
            print(f"[SpatialRetriever] Error querying {table_name}: {e}")
            # Return empty but log the attempted SQL
            return [], sql_for_provenance
        
        return rows, sql_for_provenance
    
    async def health_check(self) -> bool:
        """
        Check if PostGIS is accessible and spatial tables exist.
        
        Returns:
            True if healthy and ready to serve queries
        """
        try:
            async with get_connection() as conn:
                # Check PostGIS extension
                result = await conn.fetchval("SELECT PostGIS_Version()")
                if result is None:
                    return False
                
                # Check at least one spatial table exists
                for table_name, geom_col, _, _ in self.SPATIAL_TABLES:
                    schema, table = table_name.split(".")
                    exists = await conn.fetchval("""
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema = $1 AND table_name = $2
                    """, schema, table)
                    if exists:
                        return True
                
                return False
                
        except Exception:
            return False
    
    def has_spatial_patterns(self, question: str) -> bool:
        """
        Check if the question contains patterns suggesting spatial queries.
        
        Looks for keywords like "near", "within", "meters", "km", etc.
        Also returns True if QueryRequest has spatial constraint.
        
        Args:
            question: The natural language question
            
        Returns:
            True if spatial patterns are detected
        """
        question_lower = question.lower()
        
        # Spatial keywords
        spatial_keywords = [
            "near", "nearby", "close to", "within",
            "meters", "meter", "km", "kilometers", "kilometre",
            "miles", "mile", "feet", "foot",
            "radius", "distance", "around",
            "location", "located", "coordinates",
            "latitude", "longitude", "lat", "lon",
        ]
        
        for keyword in spatial_keywords:
            if keyword in question_lower:
                return True
        
        # Coordinate patterns (e.g., "42.48, 27.48")
        import re
        coord_pattern = r'-?\d+\.?\d*\s*,\s*-?\d+\.?\d*'
        if re.search(coord_pattern, question):
            return True
        
        return False
