# DynaTrust-RAG

**DynaTrust-RAG** is a spatiotemporal Retrieval-Augmented Generation (RAG) system built on top of PostgreSQL 15, PostGIS, and pgvector.

It combines:

- semantic vector search over documentation,
- spatial queries over geospatial data,
- and structured SQL retrieval over tabular data,

and returns answers with **full provenance** and **index staleness** metadata. The goal is to serve as a **research testbed** for hybrid RAG, attribution, and freshness-aware retrieval.

---

## Features

- **Hybrid Retrieval Pipeline**
  - Automatically routes queries to:
    - **Semantic** retriever (pgvector + Gemini / OpenAI embeddings)
    - **Spatial** retriever (PostGIS `ST_DWithin` / geometry queries)
    - **Structured** retriever (SQL filters on dates, status, etc.)
  - Hybrid router merges and ranks results from multiple backends.

- **Gemini / OpenAI Embeddings**
  - Uses `text-embedding-004` (Gemini) or `text-embedding-3-small` (OpenAI), plus a configurable local dummy provider for offline testing.

- **LLM Answer Generation**
  - Multi-provider support:
    - `gemini`, `openai`, or `local` (deterministic summary)
  - Builds a structured prompt from retrieved chunks + rows.
  - Explicitly instructed to **only use provided context** and say _“I don’t know based on the available data.”_ when evidence is insufficient.

- **Full Provenance**
  - Every response includes:
    - document chunk IDs and similarity scores,
    - executed SQL statements,
    - referenced tables and row IDs,
    - which retrievers were used.
  - Designed for attribution / hallucination analysis.

- **Staleness Detection**
  - Tracks vector index freshness via `dynatrust.vector_index_metadata`.
  - Computes lag since last refresh and classifies status as `fresh`, `stale`, or `very_stale`.
  - Staleness info is passed into the LLM prompt and returned in the API response.

- **Evaluation-Ready**
  - Logs queries and answers into `dynatrust.queries` / `dynatrust.answers`.
  - `run_eval.py` (or equivalent) can measure:
    - retrieval accuracy (recall@k),
    - hallucination rate (via labeled queries),
    - latency (end-to-end timing).

---

##  Architecture

High-level flow for `POST /dynatrust/query`:

    POST /dynatrust/query
            │
            ▼
    ┌───────────────────────────────┐
    │        QueryClassifier        │
    │  (detects spatial/structured/ │
    │       semantic intent)        │
    └───────────────────────────────┘
            │
       ┌────┼───────────────┐
       ▼    ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌───────────┐
    │ Semantic │   │ Spatial  │   │ Structured│
    │Retriever │   │Retriever │   │ Retriever │
    │(pgvector)│   │(PostGIS) │   │ (SQL)     │
    └──────────┘   └──────────┘   └───────────┘
       │            │                │
       └────────────┼────────────────┘
                    ▼
          ┌──────────────────────┐
          │ HybridRetrievalRouter│
          │  (merge & normalize) │
          └──────────────────────┘
                    │
                    ▼
          ┌──────────────────────┐
          │    AnswerGenerator   │
          │ (LLM + provenance +  │
          │   staleness context) │
          └──────────────────────┘
                    │
                    ▼
               QueryResponse (JSON)

---

##  Quick Start

### 1. Create and activate a virtualenv

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

### 2. Configure environment

    cp .env.example .env
    # Edit .env with your API keys and DB credentials

Typical `.env` fields:

    GEMINI_API_KEY=your_gemini_key
    OPENAI_API_KEY=your_openai_key   # optional
    POSTGRES_HOST=localhost
    POSTGRES_PORT=5432
    POSTGRES_USER=postgres
    POSTGRES_PASSWORD=
    POSTGRES_DB=atlas4d

    DYNATRUST_EMBEDDING_PROVIDER=gemini     # gemini | openai | local
    DYNATRUST_LLM_PROVIDER=gemini           # gemini | openai | local

### 3. Setup PostgreSQL schema

Requires PostgreSQL 15 with `pgvector` and PostGIS installed.

    psql -U postgres -d atlas4d -f sql/schema/002_dynatrust_rag.sql

This creates tables in the `dynatrust` schema, including:

- `dynatrust.document_chunks` (text + `VECTOR(768)` embedding)
- `dynatrust.vector_index_metadata`
- `dynatrust.queries`, `dynatrust.answers`, `dynatrust.gold_labels`
- any `assets` / `spatial_points` tables used by spatial/structured retrievers

### 4. Ingest documents

Ingest `.md` / `.txt` docs into `dynatrust.document_chunks`:

    # Adjust module path if the package is namespaced
    python -m dynatrust_rag.ingest_docs ./docs

This will:

- chunk documents (markdown-aware or fixed size),
- embed each chunk (Gemini/OpenAI/local),
- store text + embedding in `dynatrust.document_chunks`.

### 5. Run the API server

    uvicorn dynatrust_rag.main:app --port 8090

### 6. Send a query

    curl -X POST http://localhost:8090/dynatrust/query \
      -H "Content-Type: application/json" \
      -d '{
            "question": "What is Atlas4D?",
            "include_provenance": true
          }'

---

## ⚙️ Configuration Reference

| Variable                        | Description                              | Default     |
|---------------------------------|------------------------------------------|-------------|
| `GEMINI_API_KEY`                | Google Gemini API key                    | _required_  |
| `OPENAI_API_KEY`                | OpenAI API key                           | (optional)  |
| `POSTGRES_HOST`                 | PostgreSQL host                          | `localhost` |
| `POSTGRES_PORT`                 | PostgreSQL port                          | `5432`      |
| `POSTGRES_USER`                 | PostgreSQL user                          | `postgres`  |
| `POSTGRES_PASSWORD`             | PostgreSQL password                      | `""`        |
| `POSTGRES_DB`                   | PostgreSQL database name                 | `atlas4d`   |
| `DYNATRUST_EMBEDDING_PROVIDER`  | `gemini`, `openai`, or `local`           | `gemini`    |
| `DYNATRUST_LLM_PROVIDER`        | `gemini`, `openai`, or `local`           | `gemini`    |

---

##  Example API Response

A typical response looks like:

    {
      "query_id": "2fe99c55-ac7f-45c6-b92a-363859c57666",
      "answer": "Based on the retrieved documents, Atlas4D Base unifies spatial, time series, and vector workloads in a single PostgreSQL stack...",
      "query_type": "text_only",
      "processing_time_ms": 498.3,
      "provenance": {
        "chunk_ids": [
          "docs/blog/WHY_ATLAS4D.md#chunk_7",
          "docs/README.md#chunk_0"
        ],
        "similarity_scores": [0.75, 0.68],
        "sql_executed": [
          "SELECT ... FROM dynatrust.document_chunks ORDER BY embedding <-> $1 LIMIT 20"
        ],
        "retrievers_used": ["semantic"]
      },
      "staleness_info": {
        "vector_index_lag_seconds": 37.2,
        "status": "fresh",
        "used_semantic_results": true,
        "notes": "fresh < 300s; stale < 3600s; very_stale otherwise"
      }
    }

If spatial / structured retrievers are triggered, provenance can also include:

- table names (e.g. `dynatrust.assets`, `dynatrust.spatial_points`)
- primary keys of rows used in the answer
- spatial operations (e.g. `ST_DWithin`)

---

## 📊 Evaluation

DynaTrust-RAG is designed to support experiments on:

- retrieval quality (semantic vs hybrid),
- hallucinations vs provenance,
- and index staleness.

Example usage (adjust to your script layout):

    # Evaluate retrieval accuracy for a labeled query set
    python run_eval.py --mode accuracy --config configs/eval_hybrid.yaml

    # Measure hallucination rate (using gold labels / human judgments)
    python run_eval.py --mode hallucination --limit 50

    # Latency benchmarks (p50/p95 per mode)
    python run_eval.py --mode latency --runs 100

Common metrics:

- **Recall@k** for document chunks and table rows  
- **Attribution precision/recall** (are answer entities supported by provenance?)  
- **Latency** for pure semantic vs hybrid vs staleness-aware modes  

---

##  Testing

A small component test suite is included (exact command may vary):

    pytest dynatrust_rag/test_components.py

Covers:

- config and schema wiring,
- embedding provider behavior (local provider),
- document chunking,
- hybrid retrieval router,
- LLM answer generation stubs,
- end-to-end query flow sanity checks.

---

## 📄 License

MIT
