#!/usr/bin/env python3
"""
DynaTrust-RAG Example Query Script

Demonstrates the query pipeline without requiring a running database.
Uses local providers (deterministic embeddings + dummy LLM) so it
works offline out of the box.

Usage:
    python example_query.py
    python example_query.py --question "What happened near the port?"
    python example_query.py --question "How many active assets?" --show-provenance
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ensure the project root is on the path
sys.path.insert(0, str(Path(__file__).parent))

# Force local providers before importing anything else
import os
os.environ.setdefault("DYNATRUST_EMBEDDING_PROVIDER", "local")
os.environ.setdefault("DYNATRUST_LLM_PROVIDER", "local")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DynaTrust-RAG example query")
    parser.add_argument(
        "--question", "-q",
        default="What telecom anomalies were detected near Burgas?",
        help="Question to ask (default: telecom anomalies near Burgas)",
    )
    parser.add_argument(
        "--show-provenance", "-p",
        action="store_true",
        help="Print full provenance chain",
    )
    parser.add_argument(
        "--show-staleness", "-s",
        action="store_true",
        help="Print staleness info",
    )
    parser.add_argument(
        "--validate-output", "-v",
        action="store_true",
        help="Run output schema validation on the answer",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # --- Imports (after env vars are set) ---
    from dynatrust_rag.api.schemas import (
        QueryRequest,
        QueryType,
        Provenance,
        ProvenanceStep,
        ProvenanceStepType,
        StalenessInfo,
    )
    from dynatrust_rag.retrieval.router import QueryClassifier
    from dynatrust_rag.retrieval.base import DocumentChunk, RetrievalResult
    from dynatrust_rag.llm.answerer import AnswerGenerator, LocalLLMProvider
    from dynatrust_rag.attribution.provenance import ProvenanceBuilder
    from dynatrust_rag.validation import OutputSchemaValidator

    # --- 1. Classify the query ---
    request = QueryRequest(question=args.question)
    classifier = QueryClassifier()
    classification = classifier.classify(request)

    print(f"Question : {args.question}")
    print(f"Query type: {classification.query_type.value}")
    print(f"Signals   : {', '.join(classification.signals) or 'none'}")
    print(f"Retrievers: semantic={classification.use_semantic}  "
          f"spatial={classification.use_spatial}  "
          f"structured={classification.use_structured}")
    print()

    # --- 2. Simulate retrieval (no DB needed) ---
    chunks = [
        DocumentChunk(
            id=1,
            chunk_id="telecom_report_2023#chunk_0",
            text="Anomaly A-2291 was detected at cell tower BG-042 near Burgas port "
                 "on 2023-11-15. Signal degradation of 12 dB over 3 hours.",
            score=0.92,
            source_doc="telecom_report_2023.pdf",
        ),
        DocumentChunk(
            id=2,
            chunk_id="telecom_report_2023#chunk_3",
            text="Follow-up inspection of tower BG-042 confirmed hardware fault in "
                 "the 1800 MHz band module. Replacement scheduled for 2023-12-01.",
            score=0.85,
            source_doc="telecom_report_2023.pdf",
        ),
    ]
    result = RetrievalResult(
        semantic_chunks=chunks,
        metadata={"retrievers_used": ["semantic"]},
    )

    print(f"Retrieved {result.total_results} results ({len(chunks)} chunks)")

    # --- 3. Build provenance ---
    from dynatrust_rag.api.schemas import RowReference
    prov_builder = ProvenanceBuilder()
    prov_builder.add_chunk_step(
        chunk_ids=[c.chunk_id for c in chunks],
        similarity_scores=[c.score for c in chunks],
    )
    prov_builder.add_sql_step(
        query="SELECT * FROM anomalies WHERE region = $1",
        tables=["anomalies"],
        rows=[RowReference(table="anomalies", id="A-2291")],
    )
    provenance = prov_builder.build()
    # Add source docs for grounding
    provenance.source_docs = [c.source_doc for c in chunks if c.source_doc]

    # --- 4. Generate answer ---
    generator = AnswerGenerator(provider=LocalLLMProvider())
    staleness = StalenessInfo()  # defaults to fresh
    answer = await generator.generate_answer(
        query=request,
        retrieval=result,
        provenance=provenance,
        staleness=staleness,
    )

    print(f"\n--- Answer ---")
    print(answer)

    # --- 5. Optional: validate output ---
    if args.validate_output:
        validator = OutputSchemaValidator()
        validation = validator.validate(answer, provenance)
        print(f"\n--- Output Validation ---")
        print(f"Valid          : {validation.is_valid}")
        print(f"Grounding ratio: {validation.grounding_ratio:.2f}")
        if validation.grounded_entities:
            print(f"Grounded       : {validation.grounded_entities}")
        if validation.ungrounded_entities:
            print(f"Ungrounded     : {validation.ungrounded_entities}")
        if validation.warnings:
            print(f"Warnings       : {validation.warnings}")
        if validation.violations:
            print(f"Violations     : {validation.violations}")

    # --- 6. Optional: show provenance ---
    if args.show_provenance:
        print(f"\n--- Provenance ---")
        print(json.dumps(provenance.model_dump(mode="json"), indent=2, default=str))

    # --- 7. Optional: show staleness ---
    if args.show_staleness:
        print(f"\n--- Staleness Info ---")
        print(json.dumps(staleness.model_dump(mode="json"), indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
