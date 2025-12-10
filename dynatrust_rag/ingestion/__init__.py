"""
DynaTrust-RAG Ingestion Module

Handles document ingestion and chunking for the vector store.
"""

from .chunker import DocumentChunker, Chunk, ingest_document, ingest_file

__all__ = ["DocumentChunker", "Chunk", "ingest_document", "ingest_file"]
