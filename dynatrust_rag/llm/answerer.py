"""
DynaTrust-RAG LLM Answer Generator

Generates natural-language answers from retrieval results using LLM providers.
Supports OpenAI, Gemini, and a local dummy provider for offline testing.

Configuration via environment variables:
    DYNATRUST_LLM_PROVIDER: "openai" | "gemini" | "local" (default: "local")
    DYNATRUST_LLM_MODEL: model name (default varies by provider)
    OPENAI_API_KEY: required for OpenAI
    GEMINI_API_KEY: required for Gemini
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from ..api.schemas import QueryRequest, Provenance, StalenessInfo
    from ..retrieval.base import RetrievalResult

logger = logging.getLogger(__name__)

# Configuration
LLM_PROVIDER = os.getenv("DYNATRUST_LLM_PROVIDER", "local")
LLM_MODEL = os.getenv("DYNATRUST_LLM_MODEL", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")

# Default models per provider
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
    "local": "local-dummy",
}

# Token limits for context
MAX_CONTEXT_CHUNKS = 8
MAX_CHUNK_LENGTH = 500


def build_prompt(
    question: str,
    chunks: list[dict],
    structured_rows: list[dict],
    spatial_rows: list[dict],
    staleness_status: str | None,
    staleness_lag_seconds: float | None,
) -> str:
    """
    Build a structured prompt for the LLM.
    
    This function constructs the prompt with:
    - Retrieved document chunks with IDs and text
    - Structured/spatial row summaries
    - Staleness information
    - Clear instructions for answer generation
    
    Args:
        question: The user's natural language question
        chunks: List of document chunks with id, text, score
        structured_rows: List of structured query results
        spatial_rows: List of spatial query results
        staleness_status: "fresh", "stale", or "very_stale"
        staleness_lag_seconds: How many seconds behind the vector index is
        
    Returns:
        Formatted prompt string for the LLM
    """
    sections = []
    
    # System instruction
    sections.append("""You are a helpful assistant for the Atlas4D system. 
Your task is to answer questions based ONLY on the provided context.

IMPORTANT RULES:
1. Use ONLY the information from the provided context below.
2. If the context does not contain enough information to answer, respond with: "I don't know based on the available data."
3. Be concise but complete in your answers.
4. When citing information, mention which document it came from.
5. Do not make up or hallucinate information not present in the context.""")

    # Staleness warning
    if staleness_status:
        if staleness_status == "very_stale":
            lag_str = f" ({staleness_lag_seconds/3600:.1f} hours behind)" if staleness_lag_seconds else ""
            sections.append(f"""
⚠️ DATA FRESHNESS WARNING: The vector search index is VERY STALE{lag_str}.
Semantic search results may not reflect the latest data. 
Rely more heavily on structured/spatial query results if available.""")
        elif staleness_status == "stale":
            lag_str = f" ({staleness_lag_seconds/60:.0f} minutes behind)" if staleness_lag_seconds else ""
            sections.append(f"""
⚠️ DATA FRESHNESS NOTE: The vector search index is STALE{lag_str}.
Semantic results are mostly reliable but may miss very recent updates.""")
        else:
            sections.append("""
✅ DATA FRESHNESS: The vector search index is FRESH. Semantic results are reliable.""")

    # Document chunks section
    if chunks:
        sections.append("\n--- DOCUMENT CONTEXT ---")
        for i, chunk in enumerate(chunks[:MAX_CONTEXT_CHUNKS], 1):
            chunk_id = chunk.get("id", f"chunk_{i}")
            score = chunk.get("score", 0)
            text = chunk.get("text", "")[:MAX_CHUNK_LENGTH]
            if len(chunk.get("text", "")) > MAX_CHUNK_LENGTH:
                text += "..."
            sections.append(f"""
[{i}] Source: {chunk_id} (relevance: {score:.2f})
{text}""")
    else:
        sections.append("\n--- DOCUMENT CONTEXT ---\nNo relevant document chunks found.")

    # Structured rows section
    if structured_rows:
        sections.append("\n--- STRUCTURED DATA ---")
        for row in structured_rows[:5]:
            table = row.get("table", "unknown")
            pk = row.get("primary_key", "?")
            data = row.get("data", {})
            data_str = ", ".join(f"{k}={v}" for k, v in list(data.items())[:5])
            sections.append(f"• Table: {table}, ID: {pk} → {data_str}")

    # Spatial rows section
    if spatial_rows:
        sections.append("\n--- SPATIAL DATA ---")
        for row in spatial_rows[:5]:
            table = row.get("table", "unknown")
            pk = row.get("primary_key", "?")
            distance = row.get("distance_meters")
            dist_str = f", {distance:.0f}m away" if distance else ""
            data = row.get("data", {})
            data_str = ", ".join(f"{k}={v}" for k, v in list(data.items())[:3])
            sections.append(f"• Table: {table}, ID: {pk}{dist_str} → {data_str}")

    # The question
    sections.append(f"""
--- QUESTION ---
{question}

--- YOUR ANSWER ---""")

    return "\n".join(sections)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name
    
    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Generate a response from the prompt."""
        pass


class OpenAILLMProvider(LLMProvider):
    """LLM provider using OpenAI's Chat Completions API."""
    
    OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
    
    def __init__(self, model_name: str | None = None, api_key: str | None = None):
        super().__init__(model_name or os.getenv("DYNATRUST_LLM_MODEL", "") or DEFAULT_MODELS["openai"])
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")

        if not self.api_key:
            raise ValueError("OpenAI API key required for OpenAI LLM provider")
        
        logger.info(f"Initialized OpenAI LLM provider with model={self.model_name}")
    
    async def generate(self, prompt: str) -> str:
        """Generate response using OpenAI Chat Completions."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 1024,
        }
        
        # Retry with backoff
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        self.OPENAI_CHAT_URL,
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                
                return data["choices"][0]["message"]["content"].strip()
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    delay = 2 ** attempt
                    logger.warning(f"OpenAI rate limited, retrying in {delay}s")
                    await asyncio.sleep(delay)
                else:
                    raise
        
        raise RuntimeError("OpenAI API failed after retries")


class GeminiLLMProvider(LLMProvider):
    """LLM provider using Google's Gemini API."""
    
    GEMINI_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    
    def __init__(self, model_name: str | None = None, api_key: str | None = None):
        super().__init__(model_name or LLM_MODEL or DEFAULT_MODELS["gemini"])
        self.api_key = api_key or GEMINI_API_KEY
        
        if not self.api_key:
            raise ValueError("Gemini API key required for Gemini LLM provider")
        
        logger.info(f"Initialized Gemini LLM provider with model={self.model_name}")
    
    async def generate(self, prompt: str) -> str:
        """Generate response using Gemini API."""
        url = self.GEMINI_GENERATE_URL.format(model=self.model_name)
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 1024,
            },
        }
        
        # Retry with backoff
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        url,
                        params={"key": self.api_key},
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                
                # Extract text from Gemini response
                candidates = data.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
                
                return "Unable to generate response."
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    delay = 2 ** attempt
                    logger.warning(f"Gemini rate limited, retrying in {delay}s")
                    await asyncio.sleep(delay)
                else:
                    raise
        
        raise RuntimeError("Gemini API failed after retries")


class LocalLLMProvider(LLMProvider):
    """
    Local dummy LLM provider for offline testing.
    
    Returns a deterministic summary based on the context without
    actually calling an LLM. Useful for testing the pipeline.
    """
    
    def __init__(self, model_name: str | None = None):
        super().__init__(model_name or "local-dummy")
        logger.warning(
            "Using LocalLLMProvider - responses are deterministic summaries, "
            "NOT actual LLM outputs. Use only for testing."
        )
    
    async def generate(self, prompt: str) -> str:
        """Generate a deterministic summary from the prompt."""
        # Extract key info from prompt
        lines = prompt.split("\n")
        
        # Find the question
        question = ""
        for i, line in enumerate(lines):
            if "--- QUESTION ---" in line and i + 1 < len(lines):
                question = lines[i + 1].strip()
                break
        
        # Count context elements
        chunk_count = prompt.count("[Source:")
        if chunk_count == 0:
            chunk_count = prompt.count("relevance:")
        
        has_structured = "--- STRUCTURED DATA ---" in prompt and "No structured" not in prompt
        has_spatial = "--- SPATIAL DATA ---" in prompt and "No spatial" not in prompt
        
        # Find staleness status
        staleness = "unknown"
        if "FRESH" in prompt:
            staleness = "fresh"
        elif "VERY STALE" in prompt:
            staleness = "very_stale"
        elif "STALE" in prompt:
            staleness = "stale"
        
        # Build summary response
        parts = []
        
        if chunk_count > 0:
            parts.append(f"Based on {chunk_count} relevant document chunks")
        
        sources = []
        if has_structured:
            sources.append("structured database queries")
        if has_spatial:
            sources.append("spatial data")
        
        if sources:
            parts.append(f"and {', '.join(sources)}")
        
        if parts:
            intro = " ".join(parts) + ":"
        else:
            intro = "Based on the available data:"
        
        # Extract first chunk text as representative content
        first_chunk_text = ""
        for line in lines:
            if "(relevance:" in line:
                # Next non-empty line should be the text
                idx = lines.index(line)
                if idx + 1 < len(lines):
                    first_chunk_text = lines[idx + 1].strip()[:200]
                    break
        
        if first_chunk_text:
            response = f"{intro}\n\n{first_chunk_text}"
            if len(first_chunk_text) >= 200:
                response += "..."
        elif chunk_count == 0 and not has_structured and not has_spatial:
            response = "I don't know based on the available data."
        else:
            response = f"{intro} The system found relevant information but a full LLM is needed for synthesis."
        
        # Add staleness note
        if staleness == "very_stale":
            response += "\n\n⚠️ Note: This answer may not reflect the most recent data."
        
        return response


class AnswerGenerator:
    """
    Generates natural-language answers from retrieval results.
    
    Uses an LLM provider (OpenAI/Gemini/local-dummy) to synthesize
    answers from document chunks, structured rows, spatial data,
    and staleness information.
    """
    
    def __init__(self, provider: LLMProvider | None = None):
        """
        Initialize the answer generator.
        
        Args:
            provider: LLM provider to use. If None, creates one based on config.
        """
        if provider is None:
            provider = _create_default_provider()
        self.provider = provider
    
    async def generate_answer(
        self,
        query: "QueryRequest",
        retrieval: "RetrievalResult",
        provenance: "Provenance | None",
        staleness: "StalenessInfo | None",
    ) -> str:
        """
        Generate a natural-language answer from retrieval results.
        
        Args:
            query: The original query request
            retrieval: Results from hybrid retrieval
            provenance: Provenance information (for reference)
            staleness: Staleness information for the vector index
            
        Returns:
            Natural language answer string
        """
        # Extract chunks for prompt
        chunks = [
            {
                "id": chunk.chunk_id or f"chunk_{chunk.id}",
                "text": chunk.text,
                "score": chunk.score or 0.0,
            }
            for chunk in retrieval.semantic_chunks
        ]
        
        # Extract structured rows
        structured_rows = [
            {
                "table": row.table_name,
                "primary_key": row.primary_key,
                "data": row.data,
            }
            for row in retrieval.structured_rows
        ]
        
        # Extract spatial rows
        spatial_rows = [
            {
                "table": row.table_name,
                "primary_key": row.primary_key,
                "distance_meters": row.distance_meters,
                "data": row.data,
            }
            for row in retrieval.spatial_rows
        ]
        
        # Extract staleness info
        staleness_status = None
        staleness_lag = None
        if staleness:
            if staleness.staleness_detected:
                lag = staleness.vector_index_lag_seconds
                if lag and lag > 3600:
                    staleness_status = "very_stale"
                elif lag and lag > 300:
                    staleness_status = "stale"
                else:
                    staleness_status = "stale"
                staleness_lag = lag
            else:
                staleness_status = "fresh"
        
        # Build the prompt
        prompt = build_prompt(
            question=query.question,
            chunks=chunks,
            structured_rows=structured_rows,
            spatial_rows=spatial_rows,
            staleness_status=staleness_status,
            staleness_lag_seconds=staleness_lag,
        )
        
        # Generate answer
        try:
            answer = await self.provider.generate(prompt)
            return answer
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            # Fallback to a simple summary
            if chunks:
                return f"Found {len(chunks)} relevant documents. Top match: {chunks[0]['text'][:200]}..."
            return "I encountered an error generating the answer. Please try again."


def _create_default_provider() -> LLMProvider:
    """Create the default LLM provider based on configuration."""
    provider_name = os.getenv("DYNATRUST_LLM_PROVIDER", "local").lower()

    if provider_name == "openai":
        try:
            return OpenAILLMProvider()
        except ValueError as e:
            logger.warning(f"Failed to create OpenAI provider: {e}, falling back to local")
            return LocalLLMProvider()
    
    elif provider_name == "gemini" or provider_name == "google":
        try:
            return GeminiLLMProvider()
        except ValueError as e:
            logger.warning(f"Failed to create Gemini provider: {e}, falling back to local")
            return LocalLLMProvider()
    
    elif provider_name == "local":
        return LocalLLMProvider()
    
    else:
        logger.warning(f"Unknown LLM provider '{provider_name}', using local")
        return LocalLLMProvider()


# Singleton instance
_answer_generator: AnswerGenerator | None = None


async def get_answer_generator() -> AnswerGenerator:
    """Get the singleton AnswerGenerator instance."""
    global _answer_generator
    if _answer_generator is None:
        _answer_generator = AnswerGenerator()
    return _answer_generator


def reset_answer_generator() -> None:
    """Reset the singleton (for testing)."""
    global _answer_generator
    _answer_generator = None
