#!/usr/bin/env python3
"""
Quick validation script for DynaTrust-RAG components.

Tests the embedding provider and chunker without needing a database.
Run from the atlas4d-base directory:

    python services/dynatrust_rag/test_components.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


async def test_embedding_provider():
    """Test the embedding provider."""
    print("\n" + "=" * 50)
    print("Testing Embedding Provider")
    print("=" * 50)
    
    from services.dynatrust_rag.embedding import get_default_embedding_provider, EMBEDDING_DIM
    
    try:
        provider = await get_default_embedding_provider()
        print(f"✓ Provider initialized: {provider.__class__.__name__}")
        print(f"  Model: {provider.model_name}")
        print(f"  Target dimension: {provider.dimension}")
    except Exception as e:
        print(f"✗ Failed to initialize provider: {e}")
        return False
    
    # Test single embedding
    test_text = "What are the anomalies detected near the telecom tower?"
    try:
        embedding = await provider.embed_text(test_text)
        print(f"✓ embed_text() returned {len(embedding)} dimensions")
        assert len(embedding) == EMBEDDING_DIM, f"Expected {EMBEDDING_DIM}, got {len(embedding)}"
        print(f"  First 5 values: {embedding[:5]}")
    except Exception as e:
        print(f"✗ embed_text() failed: {e}")
        return False
    
    # Test batch embedding
    test_batch = [
        "First document about sensors",
        "Second document about weather",
        "Third document about infrastructure",
    ]
    try:
        embeddings = await provider.embed_batch(test_batch)
        print(f"✓ embed_batch() returned {len(embeddings)} embeddings")
        for i, emb in enumerate(embeddings):
            assert len(emb) == EMBEDDING_DIM
        print(f"  All embeddings have correct dimension ({EMBEDDING_DIM})")
    except Exception as e:
        print(f"✗ embed_batch() failed: {e}")
        return False
    
    return True


def test_chunker():
    """Test the document chunker."""
    print("\n" + "=" * 50)
    print("Testing Document Chunker")
    print("=" * 50)
    
    from services.dynatrust_rag.ingestion import DocumentChunker, Chunk
    
    chunker = DocumentChunker(chunk_size=200, chunk_overlap=20)
    print(f"✓ Chunker initialized (size={chunker.chunk_size}, overlap={chunker.chunk_overlap})")
    
    # Test markdown chunking
    test_doc = """# Introduction

This is a test document for DynaTrust-RAG. It contains multiple sections
to test the chunking functionality.

## Section One

This section talks about the first topic. It has enough content to
potentially be split into multiple chunks depending on the configuration.

## Section Two

This section covers the second topic. We want to make sure that
markdown headers are respected during chunking.

### Subsection 2.1

A nested subsection with more details about the topic.
"""
    
    chunks = chunker.chunk_document(
        doc_id="test_doc",
        content=test_doc,
        source_type="documentation",
        strategy="markdown",
    )
    
    print(f"✓ Chunked document into {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        preview = chunk.content[:50].replace("\n", " ")
        print(f"  Chunk {i}: {len(chunk.content)} chars - '{preview}...'")
    
    # Test fixed chunking
    long_text = "This is a sentence. " * 50
    fixed_chunks = chunker.chunk_document(
        doc_id="long_doc",
        content=long_text,
        strategy="fixed",
    )
    print(f"✓ Fixed chunking: {len(fixed_chunks)} chunks from {len(long_text)} chars")
    
    return True


def test_config():
    """Test configuration loading."""
    print("\n" + "=" * 50)
    print("Testing Configuration")
    print("=" * 50)
    
    from services.dynatrust_rag.config import get_config
    
    config = get_config()
    print(f"✓ Config loaded")
    print(f"  Database: {config.database.host}:{config.database.port}/{config.database.database}")
    print(f"  Embedding provider: {config.embedding.provider}")
    print(f"  Embedding model: {config.embedding.model}")
    print(f"  Embedding dimension: {config.embedding.dimension}")
    print(f"  Vector similarity threshold: {config.vector.similarity_threshold}")
    
    return True


def test_schemas():
    """Test Pydantic schemas."""
    print("\n" + "=" * 50)
    print("Testing API Schemas")
    print("=" * 50)
    
    from services.dynatrust_rag.api.schemas import QueryRequest, QueryResponse, Provenance
    
    # Test QueryRequest
    request = QueryRequest(
        question="Show anomalies near 42.5, 27.5 within 5km",
        include_provenance=True,
    )
    print(f"✓ QueryRequest created")
    print(f"  question: {request.question}")
    
    return True


async def test_retriever_base():
    """Test retriever base classes."""
    print("\n" + "=" * 50)
    print("Testing Retriever Base Classes")
    print("=" * 50)
    
    from services.dynatrust_rag.retrieval.base import (
        DocumentChunk, StructuredRow, SpatialRow, RetrievalResult
    )
    
    # Create sample objects
    chunk = DocumentChunk(
        id=1,
        chunk_id="doc1#chunk_0",
        text="Sample chunk content",
        score=0.85,
        source_doc="docs/README.md",
    )
    print(f"✓ DocumentChunk created: {chunk.chunk_id} (score={chunk.score})")
    
    result = RetrievalResult(
        semantic_chunks=[chunk],
        executed_sql=["SELECT * FROM chunks"],
        metadata={"retrievers_used": ["semantic"]},
    )
    print(f"✓ RetrievalResult created with {len(result.semantic_chunks)} chunks")
    
    return True


async def test_llm_answerer():
    """Test the LLM AnswerGenerator."""
    print("\n" + "=" * 50)
    print("Testing LLM AnswerGenerator")
    print("=" * 50)
    
    from services.dynatrust_rag.llm.answerer import AnswerGenerator, LocalLLMProvider
    from services.dynatrust_rag.retrieval.base import DocumentChunk, RetrievalResult
    from services.dynatrust_rag.api.schemas import QueryRequest
    
    # Create a simple retrieval result
    chunks = [
        DocumentChunk(
            id=1,
            chunk_id="test#0",
            text="DynaTrust-RAG is a spatiotemporal retrieval-augmented generation system.",
            score=0.95,
            source_doc="docs/README.md",
        ),
        DocumentChunk(
            id=2,
            chunk_id="test#1",
            text="It supports semantic, spatial, and structured queries with full provenance.",
            score=0.88,
            source_doc="docs/ARCHITECTURE.md",
        ),
    ]
    
    result = RetrievalResult(
        semantic_chunks=chunks,
        metadata={"retrievers_used": ["semantic"]},
    )
    
    # Test with local provider (doesn't require API key)
    provider = LocalLLMProvider()
    generator = AnswerGenerator(provider=provider)
    
    print(f"✓ AnswerGenerator initialized with LocalLLMProvider")
    
    request = QueryRequest(question="What is DynaTrust-RAG?")
    
    try:
        answer = await generator.generate_answer(
            query=request,
            retrieval=result,
            provenance=None,
            staleness=None,
        )
        print(f"✓ Answer generated ({len(answer)} chars)")
        print(f"  Preview: {answer[:100]}...")
        return True
    except Exception as e:
        print(f"✗ Answer generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_hybrid_retrieval():
    """Test the hybrid retrieval router."""
    print("\n" + "=" * 50)
    print("Testing Hybrid Retrieval Router")
    print("=" * 50)
    
    from services.dynatrust_rag.api.schemas import QueryRequest
    from services.dynatrust_rag.retrieval.router import HybridRetrievalRouter
    
    router = HybridRetrievalRouter()
    print("✓ HybridRetrievalRouter initialized")
    
    # Test query classification
    request = QueryRequest(
        question="What telecom anomalies were detected near Burgas after 2022?",
        include_provenance=True,
    )
    
    classification = router.classifier.classify(request)
    print(f"✓ Query classified as: {classification.query_type.value}")
    print(f"  Use semantic: {classification.use_semantic}")
    print(f"  Use spatial: {classification.use_spatial}")
    print(f"  Use structured: {classification.use_structured}")
    print(f"  Signals: {classification.signals}")
    
    return True


async def test_end_to_end():
    """Test the full query flow end-to-end."""
    print("\n" + "=" * 50)
    print("Testing End-to-End Query Flow")
    print("=" * 50)
    
    import os
    # Disable LLM for this test to avoid API calls
    os.environ["DYNATRUST_DISABLE_LLM"] = "1"
    
    from services.dynatrust_rag.api.schemas import QueryRequest
    from services.dynatrust_rag.retrieval.router import hybrid_retrieve
    
    request = QueryRequest(
        question="What is DynaTrust-RAG and how does it work?",
        include_provenance=True,
    )
    
    try:
        result = await hybrid_retrieve(request)
        print(f"✓ Hybrid retrieval completed")
        print(f"  Semantic chunks: {len(result.semantic_chunks)}")
        print(f"  Structured rows: {len(result.structured_rows)}")
        print(f"  Spatial rows: {len(result.spatial_rows)}")
        print(f"  Retrievers used: {result.metadata.get('retrievers_used', [])}")
        
        if result.semantic_chunks:
            top = result.semantic_chunks[0]
            print(f"  Top chunk score: {top.score:.3f}")
            print(f"  Top chunk source: {top.source_doc}")
        
        return True
    except Exception as e:
        print(f"✗ End-to-end test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("  DynaTrust-RAG Component Validation")
    print("=" * 60)
    
    results = []
    
    # Test config first
    results.append(("Config", test_config()))
    
    # Test schemas
    results.append(("Schemas", test_schemas()))
    
    # Test chunker
    results.append(("Chunker", test_chunker()))
    
    # Test retriever base
    results.append(("Retriever Base", await test_retriever_base()))
    
    # Test embedding provider
    results.append(("Embedding Provider", await test_embedding_provider()))
    
    # Test LLM answerer
    results.append(("LLM AnswerGenerator", await test_llm_answerer()))
    
    # Test hybrid retrieval
    results.append(("Hybrid Retrieval", await test_hybrid_retrieval()))
    
    # Test end-to-end
    results.append(("End-to-End Query", await test_end_to_end()))
    
    # Summary
    print("\n" + "=" * 50)
    print("Summary")
    print("=" * 50)
    
    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False
    
    print("\n" + ("All tests passed!" if all_passed else "Some tests failed."))
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
