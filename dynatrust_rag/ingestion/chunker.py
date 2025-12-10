"""
DynaTrust-RAG Document Chunker

Handles chunking of documents for vector embedding and storage.

Design:
- Splits documents into semantic chunks
- Preserves document structure and hierarchy
- Supports multiple chunking strategies
- Tracks chunk metadata for provenance
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import hashlib


@dataclass
class Chunk:
    """
    A single chunk of a document.
    
    Attributes:
        chunk_id: Unique identifier (format: doc_id#chunk_index)
        doc_id: Source document identifier
        chunk_index: Index within the document
        content: The text content of the chunk
        source_type: Type of source (documentation, api, schema, etc.)
        metadata: Additional metadata
        created_at: When the chunk was created
    """
    chunk_id: str
    doc_id: str
    chunk_index: int
    content: str
    source_type: str = "documentation"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def content_hash(self) -> str:
        """Get a hash of the content for deduplication."""
        return hashlib.md5(self.content.encode()).hexdigest()


class DocumentChunker:
    """
    Chunks documents for vector embedding.
    
    Supports multiple chunking strategies:
    - Fixed size with overlap
    - Sentence-based
    - Paragraph-based
    - Markdown section-based
    """
    
    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        min_chunk_size: int = 100,
    ):
        """
        Initialize the chunker.
        
        Args:
            chunk_size: Target size for each chunk in characters
            chunk_overlap: Overlap between consecutive chunks
            min_chunk_size: Minimum chunk size (smaller chunks are merged)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
    
    def chunk_document(
        self,
        doc_id: str,
        content: str,
        source_type: str = "documentation",
        strategy: str = "fixed",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Chunk]:
        """
        Chunk a document using the specified strategy.
        
        Args:
            doc_id: Unique document identifier
            content: Full document content
            source_type: Type of document
            strategy: Chunking strategy (fixed, sentence, paragraph, markdown)
            metadata: Additional metadata to attach to chunks
            
        Returns:
            List of Chunk objects
        """
        if strategy == "fixed":
            texts = self._chunk_fixed(content)
        elif strategy == "sentence":
            texts = self._chunk_sentences(content)
        elif strategy == "paragraph":
            texts = self._chunk_paragraphs(content)
        elif strategy == "markdown":
            texts = self._chunk_markdown(content)
        else:
            texts = self._chunk_fixed(content)
        
        chunks = []
        for idx, text in enumerate(texts):
            chunk = Chunk(
                chunk_id=f"{doc_id}#chunk_{idx}",
                doc_id=doc_id,
                chunk_index=idx,
                content=text,
                source_type=source_type,
                metadata={
                    **(metadata or {}),
                    "strategy": strategy,
                    "chunk_size": len(text),
                },
            )
            chunks.append(chunk)
        
        return chunks
    
    def _chunk_fixed(self, content: str) -> List[str]:
        """
        Fixed-size chunking with overlap.
        
        Args:
            content: Text to chunk
            
        Returns:
            List of text chunks
        """
        chunks = []
        start = 0
        content_len = len(content)
        
        while start < content_len:
            end = start + self.chunk_size
            
            # Try to break at a sentence boundary
            if end < content_len:
                # Look for sentence endings near the boundary
                for delim in ['. ', '.\n', '! ', '? ']:
                    pos = content.rfind(delim, start + self.min_chunk_size, end + 50)
                    if pos != -1:
                        end = pos + len(delim)
                        break
            
            chunk_text = content[start:end].strip()
            if len(chunk_text) >= self.min_chunk_size or start + self.chunk_size >= content_len:
                chunks.append(chunk_text)
            
            start = end - self.chunk_overlap
            if start >= content_len:
                break
        
        return chunks
    
    def _chunk_sentences(self, content: str) -> List[str]:
        """
        Sentence-based chunking.
        
        Groups sentences until reaching the target size.
        
        Args:
            content: Text to chunk
            
        Returns:
            List of text chunks
        """
        # Simple sentence splitting
        sentences = re.split(r'(?<=[.!?])\s+', content)
        
        chunks = []
        current_chunk = []
        current_size = 0
        
        for sentence in sentences:
            sentence_len = len(sentence)
            
            if current_size + sentence_len > self.chunk_size and current_chunk:
                chunks.append(' '.join(current_chunk))
                # Keep some overlap
                overlap_sentences = current_chunk[-1:] if current_chunk else []
                current_chunk = overlap_sentences
                current_size = sum(len(s) for s in current_chunk)
            
            current_chunk.append(sentence)
            current_size += sentence_len
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks
    
    def _chunk_paragraphs(self, content: str) -> List[str]:
        """
        Paragraph-based chunking.
        
        Groups paragraphs until reaching the target size.
        
        Args:
            content: Text to chunk
            
        Returns:
            List of text chunks
        """
        paragraphs = re.split(r'\n\s*\n', content)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        chunks = []
        current_chunk = []
        current_size = 0
        
        for para in paragraphs:
            para_len = len(para)
            
            if current_size + para_len > self.chunk_size and current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
            
            current_chunk.append(para)
            current_size += para_len
        
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
        
        return chunks
    
    def _chunk_markdown(self, content: str) -> List[str]:
        """
        Markdown section-based chunking.
        
        Splits on markdown headers, keeping each section together
        when possible.
        
        Args:
            content: Markdown text to chunk
            
        Returns:
            List of text chunks
        """
        # Split on markdown headers
        sections = re.split(r'\n(?=#+\s)', content)
        sections = [s.strip() for s in sections if s.strip()]
        
        chunks = []
        
        for section in sections:
            if len(section) <= self.chunk_size:
                chunks.append(section)
            else:
                # Section is too large, chunk it further
                sub_chunks = self._chunk_fixed(section)
                chunks.extend(sub_chunks)
        
        return chunks


async def ingest_document(
    conn,
    provider,
    source_doc: str,
    text: str,
    source_type: str = "documentation",
    chunk_strategy: str = "markdown",
    metadata: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Chunk a document, embed each chunk, and insert into dynatrust.document_chunks.
    
    This is the primary ingestion function that orchestrates the full pipeline:
    1. Split document into chunks using DocumentChunker
    2. Generate embeddings for each chunk using EmbeddingProvider
    3. Insert chunks with embeddings into the database
    
    Args:
        conn: asyncpg database connection
        provider: EmbeddingProvider instance for generating embeddings
        source_doc: Document identifier (e.g., file path or URL)
        text: Full document text content
        source_type: Type of document (documentation, api, schema, etc.)
        chunk_strategy: Chunking strategy (fixed, sentence, paragraph, markdown)
        metadata: Additional metadata to attach to all chunks
        
    Returns:
        Number of chunks successfully inserted
        
    Raises:
        Exception: If database insertion fails (after logging)
        
    Example:
        provider = await get_default_embedding_provider()
        async with pool.acquire() as conn:
            count = await ingest_document(
                conn=conn,
                provider=provider,
                source_doc="docs/README.md",
                text=readme_content,
                source_type="documentation",
            )
            print(f"Inserted {count} chunks")
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Create chunker and split document
    chunker = DocumentChunker(
        chunk_size=512,
        chunk_overlap=50,
        min_chunk_size=100,
    )
    
    chunks = chunker.chunk_document(
        doc_id=source_doc,
        content=text,
        source_type=source_type,
        strategy=chunk_strategy,
        metadata=metadata,
    )
    
    if not chunks:
        logger.warning(f"No chunks generated for document: {source_doc}")
        return 0
    
    logger.info(f"Generated {len(chunks)} chunks for document: {source_doc}")
    
    # Generate embeddings in batch for efficiency
    chunk_texts = [chunk.content for chunk in chunks]
    
    try:
        embeddings = await provider.embed_batch(chunk_texts)
        logger.debug(f"Generated {len(embeddings)} embeddings")
    except Exception as e:
        logger.error(f"Failed to generate embeddings for {source_doc}: {e}")
        raise
    
    # Insert chunks with embeddings
    inserted_count = 0
    
    for chunk, embedding in zip(chunks, embeddings):
        # Convert embedding to pgvector format string
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
        
        # Convert metadata to JSON string for asyncpg
        import json
        metadata_json = json.dumps(dict(chunk.metadata) if chunk.metadata else {})
        
        try:
            await conn.execute("""
                INSERT INTO dynatrust.document_chunks
                (doc_id, chunk_index, content, source_type, metadata, embedding, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::vector, NOW(), NOW())
                ON CONFLICT (doc_id, chunk_index) DO UPDATE SET
                    content = EXCLUDED.content,
                    source_type = EXCLUDED.source_type,
                    metadata = EXCLUDED.metadata,
                    embedding = EXCLUDED.embedding,
                    updated_at = NOW()
            """,
                chunk.doc_id,
                chunk.chunk_index,
                chunk.content,
                chunk.source_type,
                metadata_json,
                embedding_str,
            )
            inserted_count += 1
        except Exception as e:
            logger.error(f"Failed to insert chunk {chunk.chunk_id}: {e}")
            # Continue with other chunks rather than failing entirely
            continue
    
    logger.info(f"Inserted {inserted_count}/{len(chunks)} chunks for: {source_doc}")
    return inserted_count


async def ingest_file(
    conn,
    provider,
    file_path: str,
    source_type: str = "documentation",
    encoding: str = "utf-8",
) -> int:
    """
    Ingest a single file into the database.
    
    Convenience wrapper around ingest_document that handles file reading.
    
    Args:
        conn: asyncpg database connection
        provider: EmbeddingProvider instance
        file_path: Path to the file to ingest
        source_type: Type of document
        encoding: File encoding (default: utf-8)
        
    Returns:
        Number of chunks inserted
        
    Raises:
        FileNotFoundError: If file doesn't exist
        UnicodeDecodeError: If file can't be decoded
    """
    import os
    
    with open(file_path, "r", encoding=encoding) as f:
        text = f.read()
    
    # Determine chunk strategy based on file extension
    ext = os.path.splitext(file_path)[1].lower()
    if ext in (".md", ".markdown"):
        strategy = "markdown"
    elif ext in (".py", ".js", ".ts", ".go", ".rs"):
        strategy = "fixed"  # Code files work better with fixed chunking
    else:
        strategy = "paragraph"
    
    return await ingest_document(
        conn=conn,
        provider=provider,
        source_doc=file_path,
        text=text,
        source_type=source_type,
        chunk_strategy=strategy,
        metadata={"file_extension": ext},
    )
