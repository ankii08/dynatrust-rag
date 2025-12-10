"""
DynaTrust-RAG Database Connection

Manages the asyncpg connection pool for DynaTrust-RAG.
Provides a clean interface for all retrievers to access the database.

Design:
- Singleton pattern for connection pool
- Supports injection from parent application (api-gateway)
- Lazy initialization when running standalone
- Context manager for connection acquisition
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import asyncpg

from ..config import get_config


# Global connection pool reference
_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> Optional[asyncpg.Pool]:
    """
    Get the current database connection pool.
    
    Returns the pool set by the parent application or initializes
    a new one if running standalone.
    
    Returns:
        asyncpg.Pool or None if not available
    """
    global _pool
    
    if _pool is None:
        _pool = await init_pool()
    
    return _pool


def set_pool(pool: asyncpg.Pool) -> None:
    """
    Set the database connection pool.
    
    Called by the parent application (api-gateway) to share its pool
    with the DynaTrust-RAG module.
    
    Args:
        pool: An initialized asyncpg connection pool
    """
    global _pool
    _pool = pool


async def init_pool() -> Optional[asyncpg.Pool]:
    """
    Initialize a new database connection pool.
    
    Used when running standalone or when no pool has been injected.
    
    Returns:
        Initialized asyncpg.Pool or None on failure
    """
    global _pool
    
    if _pool is not None:
        return _pool
    
    config = get_config()
    
    try:
        _pool = await asyncpg.create_pool(
            host=config.database.host,
            port=config.database.port,
            database=config.database.database,
            user=config.database.user,
            password=config.database.password,
            min_size=2,
            max_size=10,
        )
        return _pool
    except Exception as e:
        print(f"[DynaTrust-RAG] Failed to create database pool: {e}")
        return None


async def close_pool() -> None:
    """
    Close the database connection pool.
    
    Should be called during application shutdown.
    """
    global _pool
    
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_connection() -> AsyncIterator[asyncpg.Connection]:
    """
    Context manager to acquire a database connection.
    
    Usage:
        async with get_connection() as conn:
            rows = await conn.fetch("SELECT * FROM ...")
    
    Yields:
        asyncpg.Connection from the pool
        
    Raises:
        RuntimeError: If no database pool is available
    """
    pool = await get_pool()
    if pool is None:
        raise RuntimeError("Database pool not available")
    
    async with pool.acquire() as conn:
        yield conn


async def execute_query(
    sql: str,
    *args,
    fetch_one: bool = False,
    fetch_all: bool = True,
) -> Optional[list]:
    """
    Execute a SQL query and return results.
    
    Convenience function for simple queries.
    
    Args:
        sql: The SQL query string
        *args: Query parameters
        fetch_one: If True, return only the first row
        fetch_all: If True, return all rows (default)
        
    Returns:
        Query results as a list of Record objects, single Record, or None
    """
    async with get_connection() as conn:
        if fetch_one:
            return await conn.fetchrow(sql, *args)
        elif fetch_all:
            return await conn.fetch(sql, *args)
        else:
            return await conn.execute(sql, *args)
