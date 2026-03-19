"""Tests for LLM answer generation."""

import pytest

from dynatrust_rag.llm.answerer import (
    AnswerGenerator,
    LocalLLMProvider,
    build_prompt,
)
from dynatrust_rag.retrieval.base import DocumentChunk, RetrievalResult
from dynatrust_rag.api.schemas import QueryRequest


class TestBuildPrompt:
    def test_includes_question(self):
        prompt = build_prompt(
            question="What is Atlas4D?",
            chunks=[], structured_rows=[], spatial_rows=[],
            staleness_status=None, staleness_lag_seconds=None,
        )
        assert "What is Atlas4D?" in prompt

    def test_includes_chunks(self):
        chunks = [{"id": "doc#0", "text": "Atlas4D is a system.", "score": 0.9}]
        prompt = build_prompt(
            question="What?", chunks=chunks,
            structured_rows=[], spatial_rows=[],
            staleness_status=None, staleness_lag_seconds=None,
        )
        assert "Atlas4D is a system." in prompt
        assert "0.90" in prompt

    def test_staleness_warning_fresh(self):
        prompt = build_prompt(
            question="Q", chunks=[], structured_rows=[], spatial_rows=[],
            staleness_status="fresh", staleness_lag_seconds=None,
        )
        assert "FRESH" in prompt

    def test_staleness_warning_very_stale(self):
        prompt = build_prompt(
            question="Q", chunks=[], structured_rows=[], spatial_rows=[],
            staleness_status="very_stale", staleness_lag_seconds=7200,
        )
        assert "VERY STALE" in prompt

    def test_grounding_instruction(self):
        prompt = build_prompt(
            question="Q", chunks=[], structured_rows=[], spatial_rows=[],
            staleness_status=None, staleness_lag_seconds=None,
        )
        assert "ONLY" in prompt
        assert "I don't know" in prompt


class TestLocalLLMProvider:
    @pytest.mark.asyncio
    async def test_returns_string(self):
        provider = LocalLLMProvider()
        result = await provider.generate("Test prompt\n--- QUESTION ---\nHello\n--- YOUR ANSWER ---")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_no_context_says_dont_know(self):
        provider = LocalLLMProvider()
        prompt = build_prompt(
            question="Something obscure",
            chunks=[], structured_rows=[], spatial_rows=[],
            staleness_status=None, staleness_lag_seconds=None,
        )
        result = await provider.generate(prompt)
        assert "don't know" in result.lower() or "available data" in result.lower()


class TestAnswerGenerator:
    @pytest.mark.asyncio
    async def test_generate_answer_with_chunks(self):
        chunks = [
            DocumentChunk(id=1, chunk_id="test#0", text="DynaTrust-RAG is a RAG system.", score=0.95, source_doc="README.md"),
            DocumentChunk(id=2, chunk_id="test#1", text="It supports hybrid retrieval.", score=0.88, source_doc="ARCH.md"),
        ]
        result = RetrievalResult(
            semantic_chunks=chunks,
            metadata={"retrievers_used": ["semantic"]},
        )
        generator = AnswerGenerator(provider=LocalLLMProvider())
        request = QueryRequest(question="What is DynaTrust-RAG?")
        answer = await generator.generate_answer(
            query=request, retrieval=result, provenance=None, staleness=None,
        )
        assert isinstance(answer, str)
        assert len(answer) > 10

    @pytest.mark.asyncio
    async def test_generate_answer_empty_retrieval(self):
        result = RetrievalResult(metadata={"retrievers_used": []})
        generator = AnswerGenerator(provider=LocalLLMProvider())
        request = QueryRequest(question="Unknown topic")
        answer = await generator.generate_answer(
            query=request, retrieval=result, provenance=None, staleness=None,
        )
        assert isinstance(answer, str)
