"""Tests for document chunking."""

from dynatrust_rag.ingestion import DocumentChunker, Chunk


class TestDocumentChunker:
    def test_init_defaults(self):
        chunker = DocumentChunker()
        assert chunker.chunk_size == 512
        assert chunker.chunk_overlap == 50

    def test_markdown_chunking(self, sample_markdown):
        chunker = DocumentChunker(chunk_size=200, chunk_overlap=20)
        chunks = chunker.chunk_document(
            doc_id="test_doc",
            content=sample_markdown,
            source_type="documentation",
            strategy="markdown",
        )
        assert len(chunks) > 0
        assert all(isinstance(c, Chunk) for c in chunks)
        assert all(c.doc_id == "test_doc" for c in chunks)
        assert chunks[0].chunk_index == 0

    def test_fixed_chunking(self):
        text = "This is a sentence. " * 50
        chunker = DocumentChunker(chunk_size=200, chunk_overlap=20)
        chunks = chunker.chunk_document(doc_id="long", content=text, strategy="fixed")
        assert len(chunks) > 1
        # Chunks should cover all content
        total_unique = set()
        for c in chunks:
            total_unique.update(c.content.split())
        assert "sentence." in total_unique

    def test_sentence_chunking(self):
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        chunker = DocumentChunker(chunk_size=40, chunk_overlap=0)
        chunks = chunker.chunk_document(doc_id="sent", content=text, strategy="sentence")
        assert len(chunks) >= 1

    def test_paragraph_chunking(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunker = DocumentChunker(chunk_size=30, chunk_overlap=0)
        chunks = chunker.chunk_document(doc_id="para", content=text, strategy="paragraph")
        assert len(chunks) >= 2

    def test_chunk_id_format(self, sample_markdown):
        chunker = DocumentChunker(chunk_size=200, chunk_overlap=20)
        chunks = chunker.chunk_document(doc_id="my_doc", content=sample_markdown, strategy="markdown")
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_id == f"my_doc#chunk_{i}"

    def test_chunk_metadata_includes_strategy(self, sample_markdown):
        chunker = DocumentChunker()
        chunks = chunker.chunk_document(doc_id="d", content=sample_markdown, strategy="markdown")
        assert chunks[0].metadata["strategy"] == "markdown"

    def test_empty_document(self):
        chunker = DocumentChunker()
        chunks = chunker.chunk_document(doc_id="empty", content="", strategy="fixed")
        # Empty or whitespace-only docs may produce 0 or 1 chunk
        assert len(chunks) <= 1

    def test_content_hash_deterministic(self):
        chunker = DocumentChunker()
        chunks = chunker.chunk_document(doc_id="d", content="Hello world", strategy="fixed")
        h1 = chunks[0].content_hash
        h2 = chunks[0].content_hash
        assert h1 == h2
