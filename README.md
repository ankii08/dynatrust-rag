# DynaTrust-RAG

**DynaTrust-RAG** is a spatiotemporal Retrieval-Augmented Generation (RAG) system built on top of PostgreSQL 15, PostGIS, and pgvector.

It combines:

- semantic vector search over documentation,
- spatial queries over geospatial data,
- and structured SQL retrieval over tabular data,

and returns answers with **full provenance** and **index staleness** metadata. The goal is to serve as a **research testbed** for hybrid RAG, attribution, and freshness-aware retrieval.

> **Status**: Research prototype (v0.1.0). Core retrieval pipeline, provenance tracking, and evaluation hooks are functional. See [Limitations](#limitations) for known gaps.

---

## Features

- **Hybrid Retrieval Pipeline**
  - Keyword-based `QueryClassifier` routes queries to:
    - **Semantic** retriever (pgvector `<->` similarity search)
    - **Spatial** retriever (PostGIS `ST_DWithin` / geography queries)
    - **Structured** retriever (parameterized SQL filters on dates, status, etc.)
  - `HybridRetrievalRouter` merges and normalizes results from multiple backends.

- **Multi-Provider Embeddings**
  - `text-embedding-004` (Gemini), `text-embedding-3-small` (OpenAI), or a deterministic local hash provider for offline testing.

- **LLM Answer Generation**
  - Multi-provider support: `gemini`, `openai`, or `local` (deterministic summary).
  - Builds a structured prompt from retrieved chunks + rows.
  - Explicitly instructed to **only use provided context** and say _"I don't know based on the available data."_ when evidence is insufficient.

- **Provenance Tracking**
  - Every response includes:
    - document chunk IDs and similarity scores,
    - executed SQL statements,
    - referenced tables and row IDs,
    - which retrievers were used.
  - Designed for attribution / hallucination analysis.

- **Staleness Detection**
  - `StalenessTracker` queries `dynatrust.vector_index_metadata` to compute lag since last vector index refresh.
  - Classifies freshness and adjusts retrieval strategy (down-weight or disable semantic results when stale).
  - Staleness info is passed into the LLM prompt and returned in the API response.

- **LLM Output Validation**
  - `OutputSchemaValidator` checks LLM answers against provenance for entity grounding.
  - Detects ungrounded identifiers (entities mentioned in the answer but absent from retrieved sources).
  - Configurable length bounds and grounding ratio thresholds.

- **Query/Answer Logging**
  - All queries and answers are logged to `dynatrust.queries` / `dynatrust.answers` with full provenance JSON.
  - `run_eval.py` can measure accuracy, hallucination rate, and latency percentiles (P50/P95/P99).

---

## Architecture

High-level flow for `POST /dynatrust/query`:

    POST /dynatrust/query
            |
            v
    +-------------------------------+
    |        QueryClassifier        |
    |  (keyword-based intent        |
    |   detection: spatial /        |
    |   structured / semantic)      |
    +-------------------------------+
            |
       +----+---------------+
       v    v               v
    +----------+   +----------+   +-----------+
    | Semantic |   | Spatial  |   | Structured|
    |Retriever |   |Retriever |   | Retriever |
    |(pgvector)|   |(PostGIS) |   | (SQL)     |
    +----------+   +----------+   +-----------+
       |            |                |
       +------------+----------------+
                    v
          +----------------------+
          | HybridRetrievalRouter|
          |  (merge & normalize) |
          +----------------------+
                    |
          +---------+-----------+
          |                     |
          v                     v
    +----------------+   +----------------+
    |StalenessTracker|   |AnswerGenerator |
    |(vector_index_  |   |(LLM + context) |
    | metadata)      |   +----------------+
    +----------------+          |
          |                     v
          +--------->  QueryResponse (JSON)
                       + QueryLogger (async)

---

## Quick Start

### 1. Create and activate a virtualenv

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

### 2. Configure environment

    cp .env.example .env
    # Edit .env with your API keys and DB credentials

See `.env.example` for all supported variables. To run without external APIs, set both providers to `local`:

    DYNATRUST_EMBEDDING_PROVIDER=local
    DYNATRUST_LLM_PROVIDER=local

### 3. Setup PostgreSQL schema

Requires PostgreSQL 15+ with `pgvector` and PostGIS extensions.

    createdb atlas4d
    psql -d atlas4d -c "CREATE EXTENSION IF NOT EXISTS vector;"
    psql -d atlas4d -c "CREATE EXTENSION IF NOT EXISTS postgis;"
    psql -d atlas4d -f sql/schema/001_init.sql
    psql -d atlas4d -f sql/schema/002_dynatrust_rag.sql

Optionally load demo data:

    psql -d atlas4d -f sql/seed/demo_burgas.sql
    psql -d atlas4d -f sql/seed/demo_telecom.sql

This creates tables in the `dynatrust` schema, including:

- `dynatrust.document_chunks` (text + `VECTOR(768)` embedding + ivfflat index)
- `dynatrust.vector_index_metadata` (staleness tracking)
- `dynatrust.queries`, `dynatrust.answers`, `dynatrust.gold_labels` (evaluation)
- `dynatrust.assets` (structured retriever demo data)
- `dynatrust.spatial_points` (spatial retriever demo data)

### 4. Ingest documents

Ingest `.md` / `.txt` docs into `dynatrust.document_chunks`:

    python -m dynatrust_rag.ingest_docs ./docs

This will:

- chunk documents (markdown-aware or fixed size),
- embed each chunk (Gemini/OpenAI/local),
- store text + embedding in `dynatrust.document_chunks`.

### 5. Run the API server

    uvicorn dynatrust_rag.main:app --reload

### 6. Send a query

    curl -X POST http://localhost:8000/dynatrust/query \
      -H "Content-Type: application/json" \
      -d '{
            "question": "What telecom anomalies were detected near Burgas?",
            "spatial": {"latitude": 42.5, "longitude": 27.46, "radius_meters": 5000},
            "include_provenance": true
          }'

---

## Configuration Reference

| Variable                        | Description                              | Default        |
|---------------------------------|------------------------------------------|----------------|
| `GEMINI_API_KEY`                | Google Gemini API key                    | (optional)     |
| `OPENAI_API_KEY`                | OpenAI API key                           | (optional)     |
| `POSTGRES_HOST`                 | PostgreSQL host                          | `localhost`      |
| `POSTGRES_PORT`                 | PostgreSQL port                          | `5432`           |
| `POSTGRES_USER`                 | PostgreSQL user                          | `atlas4d_app`    |
| `POSTGRES_PASSWORD`             | PostgreSQL password                      | `""`             |
| `POSTGRES_DB`                   | PostgreSQL database name                 | `atlas4d`       |
| `DYNATRUST_EMBEDDING_PROVIDER`  | `gemini`, `openai`, or `local`           | `openai`        |
| `DYNATRUST_LLM_PROVIDER`        | `gemini`, `openai`, or `local`           | `local`         |
| `DYNATRUST_CORS_ORIGINS`        | Comma-separated allowed CORS origins     | `localhost:*`   |

---

## Example API Response

A typical response from `POST /dynatrust/query`:

```json
{
  "query_id": "f1ab235d-3d43-4e51-945b-ee43d44392d1",
  "answer": "The telecom anomalies detected near Burgas include network issues such as high latency, packet loss on switches, and power degradation in CPE devices...",
  "query_type": "hybrid",
  "processing_time_ms": 305.5,
  "provenance": {
    "steps": [
      {
        "type": "text_chunk",
        "chunk_ids": [
          "docs/case-studies/TELECOM_BURGAS_OUTLINE.md#chunk_0",
          "docs/modules/TELECOM_PROFILE.md#chunk_8"
        ],
        "similarity_scores": [0.579, 0.544]
      },
      {
        "type": "spatial",
        "tables": []
      }
    ],
    "source_docs": ["docs/case-studies/TELECOM_BURGAS_OUTLINE.md", "docs/modules/TELECOM_PROFILE.md"],
    "sql_executed": [
      "SELECT id, doc_id, ... FROM dynatrust.document_chunks ORDER BY embedding <-> '[...]'::vector LIMIT 10",
      "SELECT id, ST_AsText(geom), ST_Distance(...) FROM dynatrust.spatial_points WHERE ST_DWithin(..., 5000.0)"
    ],
    "row_references": [],
    "total_chunks_retrieved": 10,
    "total_rows_accessed": 0,
    "query_classification": "hybrid"
  },
  "staleness_info": {
    "vector_index_lag_seconds": 769,
    "last_vector_refresh_at": "2026-03-19T03:51:13Z",
    "newest_relevant_data_at": "2026-03-19T03:49:39Z",
    "used_semantic_results": true,
    "staleness_detected": false
  },
  "timestamp": "2026-03-19T04:04:03Z"
}
```

When spatial / structured retrievers are triggered, provenance also includes:

- `row_references` with table names and primary keys
- Spatial SQL in `sql_executed` (e.g., `ST_DWithin(...)`)

---

## Evaluation

`run_eval.py` supports three evaluation modes over logged query data:

    # Accuracy: token overlap and exact match against gold labels
    python run_eval.py --mode accuracy --limit 100

    # Hallucination detection: compare answer claims to provenance
    python run_eval.py --mode hallucination --limit 50

    # Latency analysis: P50/P95/P99 from logged processing times
    python run_eval.py --mode latency --limit 500

    # Run all modes
    python run_eval.py --mode all --output results.json

**Note**: Evaluation requires queries to have been logged (via the `/dynatrust/query` endpoint) and, for accuracy mode, gold labels added via `QueryLogger.add_gold_label()`.

---

## Testing

73 unit tests covering all pipeline components (no database required):

    pip install -r requirements.txt
    python -m pytest tests/ -v

Covers: config loading, Pydantic schema validation, document chunking (4 strategies), embedding providers, query classification, retrieval result merging, LLM answer generation, provenance building, attribution metrics, and output schema validation.

A quick demo script is also available:

    python example_query.py --validate-output --show-provenance

**Note**: Integration tests that involve database retrieval require a running PostgreSQL instance with the DynaTrust schema.

---

## Limitations

This is a research prototype. Known limitations:

- **Query classification** is keyword-based, not ML-based. A future version could use a fine-tuned classifier or LLM-based routing.
- **Provenance is append-only logging**, not cryptographically tamper-evident. Suitable for research evaluation but not for adversarial trust scenarios.
- **No authentication** on API endpoints. For deployment, add an auth layer (API keys, OAuth, etc.).
- **Hallucination detection** in `run_eval.py` uses token-overlap heuristics, not LLM-based fact checking.
- **Sub-500ms latency** is achievable with the local LLM provider but depends on database performance and embedding API latency when using external providers.

---

## Security

See [docs/SECURITY.md](docs/SECURITY.md) for the threat model, input validation, SQL safety, provenance auditability, and LLM output validation design.

---

## License

MIT
