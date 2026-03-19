"""Shared fixtures for DynaTrust-RAG tests."""

import os
import pytest

# Force local providers so tests never call external APIs
os.environ.setdefault("DYNATRUST_EMBEDDING_PROVIDER", "local")
os.environ.setdefault("DYNATRUST_LLM_PROVIDER", "local")
os.environ.setdefault("DYNATRUST_DISABLE_LLM", "1")


@pytest.fixture
def sample_markdown():
    """Sample markdown document for chunking tests."""
    return """# Introduction

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
