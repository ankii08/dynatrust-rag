"""
DynaTrust-RAG LLM Module

Provides answer generation using LLM providers (OpenAI, Gemini, or local dummy).
The AnswerGenerator synthesizes natural-language answers from retrieval results,
provenance, and staleness information.
"""

from .answerer import AnswerGenerator, get_answer_generator

__all__ = ["AnswerGenerator", "get_answer_generator"]
