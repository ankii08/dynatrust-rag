#!/usr/bin/env python3
"""
DynaTrust-RAG Document Ingestion CLI

Command-line tool for ingesting documents into the DynaTrust-RAG vector store.

Usage:
    python -m dynatrust_rag.ingest_docs ./sample_docs
    python -m dynatrust_rag.ingest_docs ./docs --source-type documentation
    python -m dynatrust_rag.ingest_docs ./api --extensions .md,.txt

Environment Variables:
    DYNATRUST_EMBEDDING_PROVIDER: "openai" or "local" (default: openai)
    DYNATRUST_EMBEDDING_MODEL: Model name (default: text-embedding-3-small)
    OPENAI_API_KEY: Required when using openai provider
    
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, PGPASSWORD:
        Database connection settings

Example:
    # Ingest all markdown files from docs folder
    export OPENAI_API_KEY="sk-..."
    python -m dynatrust_rag.ingest_docs ./docs

    # Use local provider for testing (no API key needed)
    export DYNATRUST_EMBEDDING_PROVIDER=local
    python -m dynatrust_rag.ingest_docs ./docs
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from dotenv import load_dotenv
load_dotenv()
import os
import sys
from pathlib import Path
from typing import List, Set

# Add parent to path for module imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dynatrust_rag.db.connection import init_pool, close_pool, get_pool
from dynatrust_rag.embedding import get_default_embedding_provider
from dynatrust_rag.ingestion import ingest_file


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ingest_docs")


# Default file extensions to process
DEFAULT_EXTENSIONS = {".txt", ".md", ".markdown", ".rst", ".log"}


def find_files(
    directory: Path,
    extensions: Set[str],
    recursive: bool = True,
) -> List[Path]:
    """
    Find all files with matching extensions in a directory.
    
    Args:
        directory: Root directory to search
        extensions: Set of file extensions to include (e.g., {".md", ".txt"})
        recursive: Whether to search subdirectories
        
    Returns:
        List of Path objects for matching files
    """
    files = []
    
    if recursive:
        for ext in extensions:
            files.extend(directory.rglob(f"*{ext}"))
    else:
        for ext in extensions:
            files.extend(directory.glob(f"*{ext}"))
    
    # Sort for deterministic ordering
    return sorted(files)


async def ingest_directory(
    directory: Path,
    extensions: Set[str],
    source_type: str,
    recursive: bool = True,
) -> tuple[int, int, int]:
    """
    Ingest all matching files from a directory.
    
    Args:
        directory: Directory containing files to ingest
        extensions: File extensions to process
        source_type: Document type for all files
        recursive: Whether to search subdirectories
        
    Returns:
        Tuple of (files_processed, total_chunks, files_failed)
    """
    # Find all matching files
    files = find_files(directory, extensions, recursive)
    
    if not files:
        logger.warning(f"No files found in {directory} with extensions {extensions}")
        return 0, 0, 0
    
    logger.info(f"Found {len(files)} files to ingest")
    
    # Initialize database pool
    await init_pool()
    pool = await get_pool()
    
    if not pool:
        logger.error("Failed to initialize database connection pool")
        return 0, 0, len(files)
    
    # Get embedding provider
    try:
        provider = await get_default_embedding_provider()
        logger.info(f"Using embedding provider: {provider.__class__.__name__}")
    except Exception as e:
        logger.error(f"Failed to initialize embedding provider: {e}")
        await close_pool()
        return 0, 0, len(files)
    
    # Process files
    files_processed = 0
    total_chunks = 0
    files_failed = 0
    
    async with pool.acquire() as conn:
        for file_path in files:
            try:
                logger.info(f"Processing: {file_path}")
                
                chunks_inserted = await ingest_file(
                    conn=conn,
                    provider=provider,
                    file_path=str(file_path),
                    source_type=source_type,
                )
                
                files_processed += 1
                total_chunks += chunks_inserted
                logger.info(f"  ✓ Inserted {chunks_inserted} chunks")
                
            except FileNotFoundError:
                logger.error(f"  ✗ File not found: {file_path}")
                files_failed += 1
            except UnicodeDecodeError as e:
                logger.error(f"  ✗ Encoding error in {file_path}: {e}")
                files_failed += 1
            except Exception as e:
                logger.error(f"  ✗ Failed to process {file_path}: {e}")
                files_failed += 1
    
    # Cleanup
    await close_pool()
    
    return files_processed, total_chunks, files_failed


def parse_extensions(ext_str: str) -> Set[str]:
    """
    Parse comma-separated extension string into a set.
    
    Args:
        ext_str: Comma-separated extensions (e.g., ".md,.txt,.rst")
        
    Returns:
        Set of normalized extensions (with leading dots)
    """
    extensions = set()
    for ext in ext_str.split(","):
        ext = ext.strip()
        if not ext.startswith("."):
            ext = "." + ext
        extensions.add(ext.lower())
    return extensions


def main():
    """Main entry point for the ingestion CLI."""
    parser = argparse.ArgumentParser(
        description="Ingest documents into DynaTrust-RAG vector store",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Ingest markdown files from docs folder
    python -m dynatrust_rag.ingest_docs ./docs

    # Ingest with specific extensions
    python -m dynatrust_rag.ingest_docs ./data --extensions .md,.txt,.log

    # Non-recursive ingestion
    python -m dynatrust_rag.ingest_docs ./data --no-recursive

    # Use local embedding provider for testing
    DYNATRUST_EMBEDDING_PROVIDER=local python -m dynatrust_rag.ingest_docs ./docs
        """,
    )
    
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory containing documents to ingest",
    )
    
    parser.add_argument(
        "--extensions", "-e",
        type=str,
        default=",".join(DEFAULT_EXTENSIONS),
        help=f"Comma-separated file extensions to process (default: {','.join(DEFAULT_EXTENSIONS)})",
    )
    
    parser.add_argument(
        "--source-type", "-t",
        type=str,
        default="documentation",
        help="Source type label for all ingested documents (default: documentation)",
    )
    
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Don't search subdirectories",
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (debug) logging",
    )
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate directory
    if not args.directory.exists():
        logger.error(f"Directory not found: {args.directory}")
        sys.exit(1)
    
    if not args.directory.is_dir():
        logger.error(f"Not a directory: {args.directory}")
        sys.exit(1)
    
    # Parse extensions
    extensions = parse_extensions(args.extensions)
    logger.info(f"Extensions to process: {extensions}")
    
    # Run ingestion
    logger.info(f"Starting ingestion from: {args.directory}")
    
    files_processed, total_chunks, files_failed = asyncio.run(
        ingest_directory(
            directory=args.directory,
            extensions=extensions,
            source_type=args.source_type,
            recursive=not args.no_recursive,
        )
    )
    
    # Print summary
    print("\n" + "=" * 50)
    print("Ingestion Summary")
    print("=" * 50)
    print(f"Files processed:  {files_processed}")
    print(f"Files failed:     {files_failed}")
    print(f"Chunks inserted:  {total_chunks}")
    print("=" * 50)
    
    if files_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
