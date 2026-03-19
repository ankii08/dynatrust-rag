"""
DynaTrust-RAG Embedding Provider

Provides a clean, configurable interface for generating text embeddings.
Supports multiple backends: OpenAI API, HuggingFace models, or local models.

Configuration via environment variables:
    DYNATRUST_EMBEDDING_PROVIDER: "openai" | "local" (default: "openai")
    DYNATRUST_EMBEDDING_MODEL: model name (default: "text-embedding-3-small")
    OPENAI_API_KEY: required when using openai provider

Usage:
    provider = await get_default_embedding_provider()
    embedding = await provider.embed_text("Hello world")
    embeddings = await provider.embed_batch(["Hello", "World"])
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from abc import ABC, abstractmethod
from typing import Sequence

import httpx

logger = logging.getLogger(__name__)

# Embedding dimension - must match VECTOR(768) in database schema
EMBEDDING_DIM = 768

# Configuration from environment
EMBEDDING_PROVIDER = os.getenv("DYNATRUST_EMBEDDING_PROVIDER", "openai")
EMBEDDING_MODEL = os.getenv("DYNATRUST_EMBEDDING_MODEL", "text-embedding-3-small")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")

# OpenAI embedding dimensions by model
OPENAI_MODEL_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class EmbeddingProvider(ABC):
    """
    Abstract base class for embedding providers.
    
    All embedding providers must implement embed_text and embed_batch methods.
    The returned embeddings must have dimension EMBEDDING_DIM (768 by default).
    """
    
    def __init__(self, model_name: str | None = None):
        """
        Initialize the embedding provider.
        
        Args:
            model_name: Optional model name override. If not provided,
                        uses DYNATRUST_EMBEDDING_MODEL env var.
        """
        self.model_name = model_name or EMBEDDING_MODEL
        self.dimension = EMBEDDING_DIM
    
    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """
        Generate an embedding vector for a single piece of text.
        
        Args:
            text: The text to embed
            
        Returns:
            List of floats with length == self.dimension
        """
        pass
    
    @abstractmethod
    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """
        Generate embedding vectors for a batch of texts.
        
        More efficient than calling embed_text repeatedly for large batches.
        
        Args:
            texts: Sequence of texts to embed
            
        Returns:
            List of embeddings, one per input text
        """
        pass
    
    def _truncate_or_pad(self, embedding: list[float]) -> list[float]:
        """
        Ensure embedding has exactly self.dimension elements.
        
        Truncates if too long, pads with zeros if too short.
        This handles model dimension mismatches gracefully.
        
        Args:
            embedding: The raw embedding from the model
            
        Returns:
            Embedding with exactly self.dimension elements
        """
        if len(embedding) == self.dimension:
            return embedding
        elif len(embedding) > self.dimension:
            # Truncate to target dimension
            return embedding[:self.dimension]
        else:
            # Pad with zeros
            return embedding + [0.0] * (self.dimension - len(embedding))


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider using OpenAI's embedding API.
    
    Requires OPENAI_API_KEY environment variable to be set.
    
    Supported models:
        - text-embedding-3-small (1536 dims, recommended)
        - text-embedding-3-large (3072 dims)
        - text-embedding-ada-002 (1536 dims, legacy)
    """
    
    OPENAI_EMBEDDING_URL = "https://api.openai.com/v1/embeddings"
    MAX_BATCH_SIZE = 100  # OpenAI limit
    
    def __init__(self, model_name: str | None = None, api_key: str | None = None):
        """
        Initialize the OpenAI embedding provider.
        
        Args:
            model_name: OpenAI model name (default: text-embedding-3-small)
            api_key: OpenAI API key. If not provided, uses OPENAI_API_KEY env var.
            
        Raises:
            ValueError: If no API key is available
        """
        super().__init__(model_name)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        
        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        # Get native dimension for this model
        self.native_dim = OPENAI_MODEL_DIMS.get(self.model_name, 1536)
        
        logger.info(
            f"Initialized OpenAI embedding provider with model={self.model_name}, "
            f"native_dim={self.native_dim}, target_dim={self.dimension}"
        )
    
    async def embed_text(self, text: str) -> list[float]:
        """
        Generate an embedding for a single text using OpenAI API.
        
        Args:
            text: The text to embed
            
        Returns:
            Embedding vector of length self.dimension
            
        Raises:
            httpx.HTTPStatusError: If API call fails
        """
        embeddings = await self.embed_batch([text])
        return embeddings[0]
    
    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """
        Generate embeddings for a batch of texts using OpenAI API.
        
        Handles batching automatically if texts exceeds MAX_BATCH_SIZE.
        
        Args:
            texts: Sequence of texts to embed
            
        Returns:
            List of embedding vectors
            
        Raises:
            httpx.HTTPStatusError: If API call fails
        """
        if not texts:
            return []
        
        all_embeddings: list[list[float]] = []
        
        # Process in batches
        for i in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = list(texts[i:i + self.MAX_BATCH_SIZE])
            batch_embeddings = await self._call_openai_api(batch)
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings
    
    async def _call_openai_api(self, texts: list[str]) -> list[list[float]]:
        """
        Make the actual API call to OpenAI embeddings endpoint.
        
        Includes exponential backoff retry for rate limiting (429 errors).
        
        Args:
            texts: Batch of texts (must be <= MAX_BATCH_SIZE)
            
        Returns:
            List of embeddings in the same order as input texts
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model_name,
            "input": texts,
        }
        
        # Use dimensions parameter for newer models that support it
        if self.model_name.startswith("text-embedding-3"):
            # Request exactly the dimension we need (if supported and <= native)
            request_dim = min(self.dimension, self.native_dim)
            payload["dimensions"] = request_dim
        
        # Retry with exponential backoff for rate limiting
        max_retries = 5
        base_delay = 2.0  # Start with 2 second delay
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        self.OPENAI_EMBEDDING_URL,
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    
                    data = response.json()
                
                # Extract embeddings and sort by index (API may return out of order)
                embeddings_data = sorted(data["data"], key=lambda x: x["index"])
                
                # Truncate or pad each embedding to target dimension
                embeddings = [
                    self._truncate_or_pad(item["embedding"])
                    for item in embeddings_data
                ]
                
                logger.debug(
                    f"OpenAI API returned {len(embeddings)} embeddings, "
                    f"usage: {data.get('usage', {})}"
                )
                
                return embeddings
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Rate limited
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Rate limited by OpenAI API. Retrying in {delay:.1f}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise  # Re-raise non-rate-limit errors
        
        # If we exhausted all retries, make one final attempt that will raise on error
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.OPENAI_EMBEDDING_URL,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        
        embeddings_data = sorted(data["data"], key=lambda x: x["index"])
        return [self._truncate_or_pad(item["embedding"]) for item in embeddings_data]


class LocalEmbeddingProvider(EmbeddingProvider):
    """
    Local embedding provider for testing and development.
    
    Generates deterministic pseudo-embeddings based on text content hash.
    NOT suitable for production - use OpenAI or HuggingFace for real embeddings.
    
    This provider is useful for:
    - Testing the ingestion pipeline without API costs
    - Development when offline
    - CI/CD testing
    """
    
    def __init__(self, model_name: str | None = None):
        """
        Initialize the local embedding provider.
        
        Args:
            model_name: Ignored for local provider, kept for interface compatibility
        """
        super().__init__(model_name or "local-hash")
        logger.warning(
            "Using LocalEmbeddingProvider - embeddings are pseudo-random hashes, "
            "NOT semantically meaningful. Use only for testing."
        )
    
    async def embed_text(self, text: str) -> list[float]:
        """
        Generate a deterministic pseudo-embedding from text hash.
        
        The embedding is computed by hashing the text and expanding
        the hash to fill the embedding dimension. Same text always
        produces same embedding.
        
        Args:
            text: The text to embed
            
        Returns:
            Pseudo-embedding vector
        """
        # Create a deterministic hash
        hash_bytes = hashlib.sha512(text.encode("utf-8")).digest()
        
        # Expand hash to fill embedding dimension
        embedding = []
        for i in range(self.dimension):
            byte_idx = i % len(hash_bytes)
            # Normalize to [-1, 1] range
            value = (hash_bytes[byte_idx] / 255.0) * 2 - 1
            embedding.append(value)
        
        return embedding
    
    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """
        Generate pseudo-embeddings for a batch of texts.
        
        Args:
            texts: Sequence of texts to embed
            
        Returns:
            List of pseudo-embedding vectors
        """
        return [await self.embed_text(text) for text in texts]


class GeminiEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider using Google's Gemini/Generative AI embedding API.
    
    Requires GEMINI_API_KEY or GOOGLE_API_KEY environment variable.
    
    Supported models:
        - text-embedding-004 (768 dims, recommended)
        - embedding-001 (768 dims, legacy)
    """
    
    GEMINI_EMBEDDING_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
    GEMINI_BATCH_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
    MAX_BATCH_SIZE = 100
    
    # Gemini model dimensions
    GEMINI_MODEL_DIMS = {
        "text-embedding-004": 768,
        "embedding-001": 768,
    }
    
    def __init__(self, model_name: str | None = None, api_key: str | None = None):
        """
        Initialize the Gemini embedding provider.
        
        Args:
            model_name: Gemini model name (default: text-embedding-004)
            api_key: Gemini API key. If not provided, uses GEMINI_API_KEY env var.
            
        Raises:
            ValueError: If no API key is available
        """
        # Default to Gemini's recommended model
        model = model_name or os.getenv("DYNATRUST_GEMINI_MODEL", "text-embedding-004")
        super().__init__(model)
        self.api_key = api_key or GEMINI_API_KEY
        
        if not self.api_key:
            raise ValueError(
                "Gemini API key required. Set GEMINI_API_KEY or GOOGLE_API_KEY "
                "environment variable or pass api_key parameter."
            )
        
        self.native_dim = self.GEMINI_MODEL_DIMS.get(self.model_name, 768)
        
        logger.info(
            f"Initialized Gemini embedding provider with model={self.model_name}, "
            f"native_dim={self.native_dim}, target_dim={self.dimension}"
        )
    
    async def embed_text(self, text: str) -> list[float]:
        """
        Generate an embedding for a single text using Gemini API.
        
        Args:
            text: The text to embed
            
        Returns:
            Embedding vector of length self.dimension
        """
        embeddings = await self.embed_batch([text])
        return embeddings[0]
    
    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """
        Generate embeddings for a batch of texts using Gemini API.
        
        Args:
            texts: Sequence of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        all_embeddings: list[list[float]] = []
        
        # Process in batches
        for i in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = list(texts[i:i + self.MAX_BATCH_SIZE])
            batch_embeddings = await self._call_gemini_api(batch)
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings
    
    async def _call_gemini_api(self, texts: list[str]) -> list[list[float]]:
        """
        Make the actual API call to Gemini embeddings endpoint.
        
        Includes exponential backoff retry for rate limiting.
        
        Args:
            texts: Batch of texts to embed
            
        Returns:
            List of embeddings
        """
        url = self.GEMINI_BATCH_URL.format(model=self.model_name)
        
        # Build batch request payload
        requests = [
            {"model": f"models/{self.model_name}", "content": {"parts": [{"text": text}]}}
            for text in texts
        ]
        
        payload = {"requests": requests}
        
        # Retry with exponential backoff
        max_retries = 5
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        url,
                        params={"key": self.api_key},
                        json=payload,
                    )
                    response.raise_for_status()
                    
                    data = response.json()
                
                # Extract embeddings
                embeddings = []
                for item in data.get("embeddings", []):
                    raw_embedding = item.get("values", [])
                    embeddings.append(self._truncate_or_pad(raw_embedding))
                
                logger.debug(f"Gemini API returned {len(embeddings)} embeddings")
                return embeddings
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Rate limited
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"Rate limited by Gemini API. Retrying in {delay:.1f}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise
        
        # Final attempt
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                params={"key": self.api_key},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        
        embeddings = []
        for item in data.get("embeddings", []):
            raw_embedding = item.get("values", [])
            embeddings.append(self._truncate_or_pad(raw_embedding))
        
        return embeddings


# Singleton instance cache
_default_provider: EmbeddingProvider | None = None


async def get_default_embedding_provider() -> EmbeddingProvider:
    """
    Get the default embedding provider based on configuration.
    
    Uses DYNATRUST_EMBEDDING_PROVIDER env var to select provider:
        - "openai": OpenAIEmbeddingProvider (requires OPENAI_API_KEY)
        - "local": LocalEmbeddingProvider (for testing)
    
    The provider is cached as a singleton for efficiency.
    
    Returns:
        Configured EmbeddingProvider instance
        
    Raises:
        ValueError: If configured provider is unknown or misconfigured
    """
    global _default_provider
    
    if _default_provider is not None:
        return _default_provider
    
    provider_name = os.getenv("DYNATRUST_EMBEDDING_PROVIDER", "openai").lower()
    
    if provider_name == "openai":
        try:
            _default_provider = OpenAIEmbeddingProvider()
        except ValueError as e:
            logger.warning(f"Failed to initialize OpenAI provider: {e}")
            logger.warning("Falling back to local provider")
            _default_provider = LocalEmbeddingProvider()
    elif provider_name == "gemini" or provider_name == "google":
        try:
            _default_provider = GeminiEmbeddingProvider()
        except ValueError as e:
            logger.warning(f"Failed to initialize Gemini provider: {e}")
            logger.warning("Falling back to local provider")
            _default_provider = LocalEmbeddingProvider()
    elif provider_name == "local":
        _default_provider = LocalEmbeddingProvider()
    else:
        raise ValueError(
            f"Unknown embedding provider: {provider_name}. "
            f"Supported: 'openai', 'gemini', 'google', 'local'"
        )
    
    return _default_provider


def reset_default_provider() -> None:
    """
    Reset the cached default provider.
    
    Useful for testing or when configuration changes at runtime.
    """
    global _default_provider
    _default_provider = None
