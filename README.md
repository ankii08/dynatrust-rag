# DynaTrust-RAG

A production-ready **spatiotemporal Retrieval-Augmented Generation** system with hybrid retrieval, full provenance tracking, and staleness detection.

## Features

- **Hybrid Retrieval**: Automatically routes queries to semantic (pgvector), spatial (PostGIS), or structured (SQL) retrievers
- **Gemini Embeddings**: Uses `text-embedding-004` for high-quality semantic similarity
- **LLM Answer Generation**: Multi-provider support (Gemini, OpenAI, local fallback)
- **Full Provenance**: Every response includes source docs, chunk IDs, SQL executed, similarity scores
- **Staleness Detection**: Tracks vector index freshness vs. live data
- **Evaluation Ready**: Query logging + scripts for accuracy/hallucination/latency analysis

## Quick Start

### 1. Setup Environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Setup Database

```bash
# Requires PostgreSQL with pgvector extension
psql -U postgres -d atlas4d -f sql/schema/002_dynatrust_rag.sql
```

### 4. Ingest Documents

```bash
python -m dynatrust_rag.ingest_docs ./docs
```

### 5. Run Server

```bash
uvicorn dynatrust_rag.main:app --port 8090
```

### 6. Query

```bash
curl -X POST http://localhost:8090/dynatrust/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Atlas4D?", "include_provenance": true}'
```

## Architecture

```
POST /dynatrust/query
        │
        ▼
┌───────────────────┐
│  QueryClassifier  │  ← Detects spatial/structured/semantic intent
└───────────────────┘
        │
   ┌────┼────┐
   ▼    ▼    ▼
┌─────┐┌─────┐┌─────┐
│Seman││Spati││Struc│  ← Parallel retrieval
│tic  ││al   ││tured│
└─────┘└─────┘└─────┘
   │    │    │
   └────┼────┘
        ▼
┌───────────────────┐
│  HybridRouter     │  ← Merge & rank results
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  AnswerGenerator  │  ← LLM synthesis with provenance
└───────────────────┘
        │
        ▼
    QueryResponse
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key | required |
| `POSTGRES_HOST` | PostgreSQL host | `localhost` |
| `POSTGRES_USER` | PostgreSQL user | `postgres` |
| `DYNATRUST_EMBEDDING_PROVIDER` | `gemini`, `openai`, `local` | `gemini` |
| `DYNATRUST_LLM_PROVIDER` | `gemini`, `openai`, `local` | `gemini` |

## API Response

```json
{
  "query_id": "uuid",
  "answer": "Based on the retrieved documents...",
  "query_type": "hybrid",
  "processing_time_ms": 245.3,
  "provenance": {
    "chunk_ids": ["docs/README.md#chunk_0", ...],
    "similarity_scores": [0.75, 0.68, ...],
    "sql_executed": [...]
  },
  "staleness_info": {
    "staleness_detected": false
  }
}
```

## Evaluation

```bash
python run_eval.py --mode accuracy
python run_eval.py --mode hallucination --limit 50
python run_eval.py --mode latency
```

## License

MIT
