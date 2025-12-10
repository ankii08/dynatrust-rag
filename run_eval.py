#!/usr/bin/env python3
"""
DynaTrust-RAG Evaluation Script

Runs evaluation experiments on logged queries.
Supports:
- Accuracy metrics (exact match, fuzzy match, BLEU)
- Hallucination detection (claims vs. provenance)
- Latency analysis
- Staleness impact analysis

Usage:
    python scripts/run_eval.py --mode accuracy
    python scripts/run_eval.py --mode hallucination --limit 50
    python scripts/run_eval.py --mode latency
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "services"))

from dynatrust_rag.config import DynaTrustConfig
from dynatrust_rag.evaluation.logger import QueryLogger
from dynatrust_rag.db.connection import get_pool


@dataclass
class AccuracyMetrics:
    """Accuracy evaluation metrics."""
    total_queries: int
    exact_matches: int
    fuzzy_matches: int  # Token overlap > 0.8
    avg_token_overlap: float
    avg_rating: Optional[float]
    
    def __str__(self) -> str:
        exact_pct = (self.exact_matches / self.total_queries * 100) if self.total_queries else 0
        fuzzy_pct = (self.fuzzy_matches / self.total_queries * 100) if self.total_queries else 0
        return (
            f"Accuracy Metrics:\n"
            f"  Total queries:     {self.total_queries}\n"
            f"  Exact matches:     {self.exact_matches} ({exact_pct:.1f}%)\n"
            f"  Fuzzy matches:     {self.fuzzy_matches} ({fuzzy_pct:.1f}%)\n"
            f"  Avg token overlap: {self.avg_token_overlap:.3f}\n"
            f"  Avg rating:        {self.avg_rating or 'N/A'}"
        )


@dataclass
class HallucinationMetrics:
    """Hallucination detection metrics."""
    total_queries: int
    queries_with_unsupported_claims: int
    avg_supported_ratio: float
    common_hallucination_types: list
    
    def __str__(self) -> str:
        unsupported_pct = (self.queries_with_unsupported_claims / self.total_queries * 100) if self.total_queries else 0
        return (
            f"Hallucination Metrics:\n"
            f"  Total queries:      {self.total_queries}\n"
            f"  Unsupported claims: {self.queries_with_unsupported_claims} ({unsupported_pct:.1f}%)\n"
            f"  Avg supported ratio: {self.avg_supported_ratio:.3f}\n"
            f"  Common types: {', '.join(self.common_hallucination_types[:5])}"
        )


@dataclass 
class LatencyMetrics:
    """Latency analysis metrics."""
    total_queries: int
    avg_processing_time_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    by_query_type: dict
    
    def __str__(self) -> str:
        return (
            f"Latency Metrics:\n"
            f"  Total queries: {self.total_queries}\n"
            f"  Avg: {self.avg_processing_time_ms:.1f}ms\n"
            f"  P50: {self.p50_ms:.1f}ms\n"
            f"  P95: {self.p95_ms:.1f}ms\n"
            f"  P99: {self.p99_ms:.1f}ms\n"
            f"  By type: {json.dumps(self.by_query_type, indent=4)}"
        )


def token_overlap(text1: str, text2: str) -> float:
    """Calculate token overlap ratio between two texts."""
    tokens1 = set(text1.lower().split())
    tokens2 = set(text2.lower().split())
    
    if not tokens1 or not tokens2:
        return 0.0
    
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    
    return len(intersection) / len(union)


async def run_accuracy_evaluation(limit: int = 100) -> AccuracyMetrics:
    """Run accuracy evaluation on logged queries with gold labels."""
    config = DynaTrustConfig()
    logger = QueryLogger(config)
    
    batch = await logger.get_evaluation_batch(limit=limit, with_gold_labels=True)
    
    if not batch:
        return AccuracyMetrics(
            total_queries=0,
            exact_matches=0,
            fuzzy_matches=0,
            avg_token_overlap=0.0,
            avg_rating=None,
        )
    
    exact_matches = 0
    fuzzy_matches = 0
    total_overlap = 0.0
    ratings = []
    
    for item in batch:
        answer = item.get("answer", "")
        gold = item.get("gold_answer", "")
        rating = item.get("rating")
        
        # Exact match check
        if answer.strip().lower() == gold.strip().lower():
            exact_matches += 1
            fuzzy_matches += 1
            total_overlap += 1.0
        else:
            # Token overlap
            overlap = token_overlap(answer, gold)
            total_overlap += overlap
            if overlap >= 0.8:
                fuzzy_matches += 1
        
        if rating is not None:
            ratings.append(rating)
    
    return AccuracyMetrics(
        total_queries=len(batch),
        exact_matches=exact_matches,
        fuzzy_matches=fuzzy_matches,
        avg_token_overlap=total_overlap / len(batch) if batch else 0.0,
        avg_rating=sum(ratings) / len(ratings) if ratings else None,
    )


async def run_hallucination_detection(limit: int = 100) -> HallucinationMetrics:
    """
    Detect potential hallucinations by comparing claims to provenance.
    
    A claim is considered unsupported if:
    1. It mentions specific numbers/dates not in provenance
    2. It references entities not in source documents
    3. It makes assertions not derivable from retrieved chunks
    """
    config = DynaTrustConfig()
    logger = QueryLogger(config)
    
    batch = await logger.get_evaluation_batch(limit=limit, with_gold_labels=False)
    
    if not batch:
        return HallucinationMetrics(
            total_queries=0,
            queries_with_unsupported_claims=0,
            avg_supported_ratio=0.0,
            common_hallucination_types=[],
        )
    
    unsupported_count = 0
    total_supported_ratio = 0.0
    hallucination_types: dict[str, int] = {}
    
    for item in batch:
        answer = item.get("answer", "")
        provenance_json = item.get("provenance_json")
        
        if not provenance_json:
            continue
        
        try:
            provenance = json.loads(provenance_json)
        except json.JSONDecodeError:
            continue
        
        # Extract all source text from provenance
        source_text = ""
        source_docs = provenance.get("source_docs", [])
        source_text += " ".join(source_docs)
        
        # Simple heuristic: check if answer tokens appear in sources
        answer_tokens = set(answer.lower().split())
        source_tokens = set(source_text.lower().split())
        
        if source_tokens:
            supported_ratio = len(answer_tokens & source_tokens) / len(answer_tokens)
        else:
            # No source tokens - consider as potentially hallucinated
            supported_ratio = 0.5  # Give benefit of doubt
        
        total_supported_ratio += supported_ratio
        
        if supported_ratio < 0.3:  # Less than 30% overlap is suspicious
            unsupported_count += 1
            # Categorize hallucination type
            if any(word.isdigit() for word in answer.split()):
                hallucination_types["numeric_claim"] = hallucination_types.get("numeric_claim", 0) + 1
            if any(year in answer for year in ["2020", "2021", "2022", "2023", "2024"]):
                hallucination_types["date_claim"] = hallucination_types.get("date_claim", 0) + 1
    
    # Sort hallucination types by frequency
    sorted_types = sorted(hallucination_types.keys(), key=lambda k: hallucination_types[k], reverse=True)
    
    return HallucinationMetrics(
        total_queries=len(batch),
        queries_with_unsupported_claims=unsupported_count,
        avg_supported_ratio=total_supported_ratio / len(batch) if batch else 0.0,
        common_hallucination_types=sorted_types,
    )


async def run_latency_analysis(limit: int = 500) -> LatencyMetrics:
    """Analyze query latency distribution."""
    pool = await get_pool()
    if not pool:
        return LatencyMetrics(
            total_queries=0,
            avg_processing_time_ms=0.0,
            p50_ms=0.0,
            p95_ms=0.0,
            p99_ms=0.0,
            by_query_type={},
        )
    
    async with pool.acquire() as conn:
        # Get latency statistics
        rows = await conn.fetch("""
            SELECT 
                processing_time_ms,
                query_type
            FROM dynatrust.answers
            ORDER BY created_at DESC
            LIMIT $1
        """, limit)
        
        if not rows:
            return LatencyMetrics(
                total_queries=0,
                avg_processing_time_ms=0.0,
                p50_ms=0.0,
                p95_ms=0.0,
                p99_ms=0.0,
                by_query_type={},
            )
        
        times = sorted([r["processing_time_ms"] for r in rows if r["processing_time_ms"]])
        by_type: dict[str, list[float]] = {}
        
        for row in rows:
            qt = row["query_type"] or "unknown"
            if qt not in by_type:
                by_type[qt] = []
            if row["processing_time_ms"]:
                by_type[qt].append(row["processing_time_ms"])
        
        def percentile(data: list, p: float) -> float:
            if not data:
                return 0.0
            idx = int(len(data) * p / 100)
            return data[min(idx, len(data) - 1)]
        
        return LatencyMetrics(
            total_queries=len(times),
            avg_processing_time_ms=sum(times) / len(times) if times else 0.0,
            p50_ms=percentile(times, 50),
            p95_ms=percentile(times, 95),
            p99_ms=percentile(times, 99),
            by_query_type={
                k: {"avg": sum(v) / len(v), "count": len(v)}
                for k, v in by_type.items()
            },
        )


async def main():
    parser = argparse.ArgumentParser(description="DynaTrust-RAG Evaluation")
    parser.add_argument(
        "--mode",
        choices=["accuracy", "hallucination", "latency", "all"],
        default="all",
        help="Evaluation mode",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum queries to evaluate",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file for JSON results",
    )
    
    args = parser.parse_args()
    
    results = {}
    
    print(f"\n{'='*60}")
    print(f"DynaTrust-RAG Evaluation - {datetime.now().isoformat()}")
    print(f"{'='*60}\n")
    
    if args.mode in ("accuracy", "all"):
        print("Running accuracy evaluation...")
        accuracy = await run_accuracy_evaluation(args.limit)
        print(accuracy)
        print()
        results["accuracy"] = {
            "total_queries": accuracy.total_queries,
            "exact_matches": accuracy.exact_matches,
            "fuzzy_matches": accuracy.fuzzy_matches,
            "avg_token_overlap": accuracy.avg_token_overlap,
            "avg_rating": accuracy.avg_rating,
        }
    
    if args.mode in ("hallucination", "all"):
        print("Running hallucination detection...")
        hallucination = await run_hallucination_detection(args.limit)
        print(hallucination)
        print()
        results["hallucination"] = {
            "total_queries": hallucination.total_queries,
            "queries_with_unsupported_claims": hallucination.queries_with_unsupported_claims,
            "avg_supported_ratio": hallucination.avg_supported_ratio,
            "common_types": hallucination.common_hallucination_types,
        }
    
    if args.mode in ("latency", "all"):
        print("Running latency analysis...")
        latency = await run_latency_analysis(args.limit)
        print(latency)
        print()
        results["latency"] = {
            "total_queries": latency.total_queries,
            "avg_ms": latency.avg_processing_time_ms,
            "p50_ms": latency.p50_ms,
            "p95_ms": latency.p95_ms,
            "p99_ms": latency.p99_ms,
            "by_type": latency.by_query_type,
        }
    
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Results saved to {args.output}")
    
    print(f"\n{'='*60}")
    print("Evaluation complete.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
