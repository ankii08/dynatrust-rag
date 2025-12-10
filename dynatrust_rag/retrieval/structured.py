"""
DynaTrust-RAG Structured Retriever

Implements SQL-based retrieval for structured queries over relational data
in PostgreSQL, handling attribute filters like dates, statuses, and types.

How it works:
1. Parses the question text for structured filters (dates, keywords)
2. Builds SQL queries with appropriate WHERE clauses
3. Returns StructuredRow objects with the matched data
4. Logs executed SQL for provenance

Current capabilities (rule-based):
- Date extraction: "after 2020", "since 2019", "before 2023"
- Time window: Uses QueryRequest.time_window if provided
- Source type filtering: Uses QueryRequest.source_types

Supported tables:
- dynatrust.assets (primary structured table for install_date, status queries)
- atlas4d.observations_core
- atlas4d.anomalies  
- atlas4d.trajectory_embeddings

Future: Replace rule-based parsing with text-to-SQL model.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..api.schemas import QueryRequest
from ..db.connection import get_connection
from .base import BaseRetriever, RetrievalResult, StructuredRow


# Default limit
DEFAULT_LIMIT = 50


class StructuredRetriever(BaseRetriever):
    """
    Structured retriever for SQL-based queries on relational data.
    
    Handles queries that involve attribute filtering:
    - Date/time constraints ("after 2020", "installed since 2019")
    - Status filters ("active", "inactive", "decommissioned")
    - Count/aggregation queries ("how many")
    
    Primary table: dynatrust.assets
        - id: UUID primary key
        - name: Asset name
        - install_date: Installation date
        - status: active/inactive/decommissioned
        - asset_type: Type classification
        - location: Text location description
    
    Features:
    - Rule-based filter extraction from natural language
    - Time window support from QueryRequest
    - Provenance tracking with full SQL
    - Extensible to additional tables
    
    Example usage:
        retriever = StructuredRetriever()
        query = QueryRequest(
            question="Show assets installed after 2022 that are active",
        )
        result = await retriever.retrieve(query, limit=50)
        for row in result.structured_rows:
            print(f"{row.table_name}:{row.primary_key} - {row.data}")
    """
    
    # Tables to query with structured filters
    # Format: (schema.table, id_column, timestamp_column, additional_columns)
    STRUCTURED_TABLES: List[Tuple[str, str, str, List[str]]] = [
        ("dynatrust.assets", "id", "install_date", ["name", "status", "asset_type", "location"]),
    ]
    
    def __init__(self, pool=None, default_limit: int = DEFAULT_LIMIT):
        """
        Initialize the structured retriever.
        
        Args:
            pool: Optional asyncpg connection pool
            default_limit: Default maximum results per table
        """
        super().__init__(pool)
        self.default_limit = default_limit
    
    async def retrieve(self, query: QueryRequest, limit: int = 50) -> RetrievalResult:
        """
        Retrieve rows matching structured filters extracted from the query.
        
        Args:
            query: QueryRequest with question and optional time_window/filters
            limit: Maximum results across all tables
            
        Returns:
            RetrievalResult with structured_rows populated and executed_sql logged
        """
        # Extract structured filters from the question
        filters = self._extract_filters(query.question)
        
        # Add explicit time window if provided
        if query.time_window:
            if query.time_window.last_n_hours:
                filters["last_n_hours"] = query.time_window.last_n_hours
            if query.time_window.start:
                filters["start_date"] = query.time_window.start
            if query.time_window.end:
                filters["end_date"] = query.time_window.end
        
        # Add source type filter if provided
        if query.source_types:
            filters["source_types"] = query.source_types
        
        all_rows: List[StructuredRow] = []
        all_sql: List[str] = []
        
        # Calculate per-table limit
        per_table_limit = max(10, limit // len(self.STRUCTURED_TABLES))
        
        for table_name, id_col, ts_col, extra_cols in self.STRUCTURED_TABLES:
            rows, sql = await self._query_structured_table(
                table_name=table_name,
                id_col=id_col,
                ts_col=ts_col,
                extra_cols=extra_cols,
                filters=filters,
                limit=per_table_limit,
            )
            all_rows.extend(rows)
            all_sql.append(sql)
        
        return RetrievalResult(
            structured_rows=all_rows[:limit],
            executed_sql=all_sql,
            metadata={
                "retrievers_used": ["structured"],
                "rows_retrieved": len(all_rows),
                "filters_applied": filters,
            },
        )
    
    def _extract_filters(self, question: str) -> Dict[str, Any]:
        """
        Extract structured filters from the question text.
        
        This is a simple rule-based implementation. Future versions
        should use a text-to-SQL model.
        
        Patterns recognized:
        - "after 2020", "since 2019" → year_after
        - "before 2023" → year_before
        - "in 2022", "from 2021" → year_exact
        - "last N hours/days" → last_n_hours/days
        
        Args:
            question: Natural language question
            
        Returns:
            Dict of extracted filter parameters
        """
        filters: Dict[str, Any] = {}
        question_lower = question.lower()
        
        # Year patterns
        # "after 2020", "since 2019"
        after_match = re.search(r'(?:after|since)\s+(\d{4})', question_lower)
        if after_match:
            year = int(after_match.group(1))
            filters["year_after"] = year
        
        # "before 2023"
        before_match = re.search(r'before\s+(\d{4})', question_lower)
        if before_match:
            year = int(before_match.group(1))
            filters["year_before"] = year
        
        # "in 2022", "from 2022"
        exact_match = re.search(r'(?:in|from)\s+(\d{4})(?:\s|$|[,.])', question_lower)
        if exact_match and "after" not in question_lower and "before" not in question_lower:
            year = int(exact_match.group(1))
            filters["year_exact"] = year
        
        # "last N hours"
        hours_match = re.search(r'last\s+(\d+)\s+hours?', question_lower)
        if hours_match:
            filters["last_n_hours"] = int(hours_match.group(1))
        
        # "last N days"
        days_match = re.search(r'last\s+(\d+)\s+days?', question_lower)
        if days_match:
            filters["last_n_hours"] = int(days_match.group(1)) * 24
        
        # Severity patterns for anomalies
        if "high severity" in question_lower or "critical" in question_lower:
            filters["min_severity"] = 4
        elif "medium severity" in question_lower:
            filters["min_severity"] = 3
        
        # Status patterns (for assets table)
        if "active" in question_lower and "inactive" not in question_lower:
            filters["status"] = "active"
        elif "inactive" in question_lower:
            filters["status"] = "inactive"
        elif "decommissioned" in question_lower:
            filters["status"] = "decommissioned"
        
        # Installed patterns (synonyms for date filters on install_date)
        installed_after = re.search(r'installed\s+(?:after|since)\s+(\d{4})', question_lower)
        if installed_after:
            filters["year_after"] = int(installed_after.group(1))
        
        installed_before = re.search(r'installed\s+before\s+(\d{4})', question_lower)
        if installed_before:
            filters["year_before"] = int(installed_before.group(1))
        
        return filters
    
    async def _query_structured_table(
        self,
        table_name: str,
        id_col: str,
        ts_col: str,
        extra_cols: List[str],
        filters: Dict[str, Any],
        limit: int,
    ) -> Tuple[List[StructuredRow], str]:
        """
        Query a single table with structured filters.
        
        Args:
            table_name: Full table name (schema.table)
            id_col: Primary key column name
            ts_col: Timestamp column name
            extra_cols: Additional columns to select
            filters: Dict of filter parameters
            limit: Maximum rows
            
        Returns:
            Tuple of (list of StructuredRow, SQL for provenance)
        """
        where_clauses: List[str] = []
        params: List[Any] = []
        param_idx = 1
        
        # Build WHERE clauses from filters
        
        # Year after filter
        if "year_after" in filters:
            year = filters["year_after"]
            where_clauses.append(f"{ts_col} >= ${param_idx}")
            params.append(datetime(year, 1, 1))
            param_idx += 1
        
        # Year before filter
        if "year_before" in filters:
            year = filters["year_before"]
            where_clauses.append(f"{ts_col} < ${param_idx}")
            params.append(datetime(year, 1, 1))
            param_idx += 1
        
        # Year exact filter
        if "year_exact" in filters:
            year = filters["year_exact"]
            where_clauses.append(f"{ts_col} >= ${param_idx}")
            params.append(datetime(year, 1, 1))
            param_idx += 1
            where_clauses.append(f"{ts_col} < ${param_idx}")
            params.append(datetime(year + 1, 1, 1))
            param_idx += 1
        
        # Last N hours filter
        if "last_n_hours" in filters:
            hours = filters["last_n_hours"]
            where_clauses.append(f"{ts_col} >= NOW() - INTERVAL '{hours} hours'")
        
        # Start/end date filters
        if "start_date" in filters:
            where_clauses.append(f"{ts_col} >= ${param_idx}")
            params.append(filters["start_date"])
            param_idx += 1
        
        if "end_date" in filters:
            where_clauses.append(f"{ts_col} <= ${param_idx}")
            params.append(filters["end_date"])
            param_idx += 1
        
        # Source types filter
        if "source_types" in filters:
            where_clauses.append(f"source_type = ANY(${param_idx})")
            params.append(filters["source_types"])
            param_idx += 1
        
        # Severity filter (for anomalies table)
        if "min_severity" in filters and "severity" in extra_cols:
            where_clauses.append(f"severity >= ${param_idx}")
            params.append(filters["min_severity"])
            param_idx += 1
        
        # Status filter (for assets table)
        if "status" in filters and "status" in extra_cols:
            where_clauses.append(f"status = ${param_idx}")
            params.append(filters["status"])
            param_idx += 1
        
        # Build the query
        cols = [id_col, ts_col] + extra_cols
        cols_str = ", ".join(cols)
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
        
        sql = f"""
            SELECT {cols_str}
            FROM {table_name}
            WHERE {where_sql}
            ORDER BY {ts_col} DESC
            LIMIT ${param_idx}
        """
        params.append(limit)
        
        # SQL for provenance (readable version)
        filters_desc = ", ".join(f"{k}={v}" for k, v in filters.items())
        sql_for_provenance = f"""
            SELECT {cols_str}
            FROM {table_name}
            WHERE {where_sql}
            ORDER BY {ts_col} DESC
            LIMIT {limit}
            -- Filters: {filters_desc}
        """
        
        rows: List[StructuredRow] = []
        
        try:
            async with get_connection() as conn:
                records = await conn.fetch(sql, *params)
                
                for record in records:
                    # Build data dict
                    data = {}
                    for key, value in record.items():
                        if key != id_col:
                            # Handle special types
                            if hasattr(value, "isoformat"):
                                data[key] = value.isoformat()
                            elif isinstance(value, (dict, list)):
                                data[key] = value
                            else:
                                data[key] = value
                    
                    row = StructuredRow(
                        table_name=table_name.split(".")[-1],
                        primary_key=record[id_col],
                        data=data,
                        score=1.0,  # Structured matches are binary
                    )
                    rows.append(row)
                    
        except Exception as e:
            print(f"[StructuredRetriever] Error querying {table_name}: {e}")
            return [], sql_for_provenance
        
        return rows, sql_for_provenance
    
    async def health_check(self) -> bool:
        """
        Check if the database is accessible and tables exist.
        
        Returns:
            True if healthy and ready
        """
        try:
            async with get_connection() as conn:
                # Check at least one table exists
                for table_name, _, _, _ in self.STRUCTURED_TABLES:
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
    
    def has_structured_patterns(self, question: str) -> bool:
        """
        Check if the question contains patterns that suggest structured retrieval.
        
        Args:
            question: The natural language question
            
        Returns:
            True if structured patterns are detected
        """
        question_lower = question.lower()
        
        # Date patterns
        date_patterns = [
            r'(?:after|since|before)\s+\d{4}',
            r'installed\s+(?:after|since|before)',
            r'last\s+\d+\s+(?:hours?|days?|weeks?)',
            r'(?:in|from)\s+\d{4}',
        ]
        
        for pattern in date_patterns:
            if re.search(pattern, question_lower):
                return True
        
        # Status patterns
        status_keywords = ["active", "inactive", "decommissioned", "status"]
        for keyword in status_keywords:
            if keyword in question_lower:
                return True
        
        # Explicit structured query hints
        structured_hints = ["how many", "count", "list all", "show all", "installed"]
        for hint in structured_hints:
            if hint in question_lower:
                return True
        
        return False
