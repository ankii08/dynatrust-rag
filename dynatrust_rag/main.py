"""
DynaTrust-RAG Standalone Application

This module provides a standalone FastAPI application for running
DynaTrust-RAG independently of the main Atlas4D gateway.

For integrated deployment, the dynatrust_router is imported and
included in the main api-gateway application.
"""

import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.router import dynatrust_router
from .db.connection import init_pool, close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events for standalone mode."""
    print("🔬 Starting DynaTrust-RAG (standalone mode)...")
    
    # Initialize database pool
    pool = await init_pool()
    if pool:
        print("✅ PostgreSQL connected")
    else:
        print("⚠️ PostgreSQL not available - some features will be limited")
    
    print("🎉 DynaTrust-RAG ready!")
    
    yield
    
    # Shutdown
    await close_pool()
    print("👋 DynaTrust-RAG stopped")


app = FastAPI(
    title="DynaTrust-RAG",
    description="""
# DynaTrust-RAG: Hybrid Retrieval with Provenance and Staleness Awareness

A research prototype for answering natural-language questions over 
dynamic spatial-relational PostgreSQL/PostGIS databases.

## Features

- **Hybrid Retrieval**: Combines semantic (pgvector), spatial (PostGIS), 
  and structured (SQL) retrieval strategies
- **Explicit Provenance**: Every answer includes machine-readable attribution 
  tracking all source data
- **Staleness Awareness**: Detects when vector indices lag behind live data 
  and adapts retrieval strategy
- **Evaluation Hooks**: Built-in logging and tables for accuracy assessment 
  and hallucination detection

## API Endpoints

- `POST /dynatrust/query` - Submit a natural language question
- `GET /dynatrust/health` - Health check with vector index status
- `GET /dynatrust/provenance/{query_id}` - Retrieve provenance for past queries
""",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the DynaTrust router
app.include_router(dynatrust_router)


@app.get("/")
async def root():
    """Root endpoint with basic info."""
    return {
        "service": "DynaTrust-RAG",
        "version": "0.1.0",
        "description": "Hybrid retrieval with provenance and staleness awareness",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
