# DynaTrust-RAG Security Model

This document describes the security-relevant design of DynaTrust-RAG and the threat model it addresses. It is written for researchers evaluating or extending the system.

> **Status**: Research prototype. The mechanisms below are implemented but have not been audited for production deployment.

---

## 1. Threat Model

DynaTrust-RAG is a hybrid RAG system that retrieves from three backends (semantic/vector, spatial/PostGIS, structured/SQL). Each backend introduces distinct attack surfaces:

| Threat | Backend | Mitigation in DynaTrust-RAG |
|---|---|---|
| **Corpus poisoning** | Semantic | Content hashing on ingested chunks (`Chunk.content_hash`); deterministic chunk IDs enable diff-based auditing |
| **Prompt injection** | LLM generation | Grounding instructions in prompt template; `build_prompt()` separates system rules from retrieved context |
| **SQL injection** | Structured | Parameterized queries via `asyncpg` (`$1`, `$2` placeholders); no string interpolation of user input into SQL |
| **Spatial spoofing** | Spatial | Pydantic validation on `SpatialConstraint` (lat ∈ [-90, 90], lon ∈ [-180, 180], radius > 0) |
| **Stale embeddings** | Semantic | `StalenessTracker` queries `vector_index_metadata` table; stale results are flagged in response and prompt |
| **Hallucination** | LLM generation | `AttributionMetrics` computes entity-level coverage scores; provenance chain enables post-hoc verification |

---

## 2. Input Validation

All user input enters through the `/dynatrust/query` endpoint and is validated by Pydantic v2 models before any processing:

- **`QueryRequest.question`**: `min_length=1`, `max_length=2000`, whitespace stripped (`str_strip_whitespace=True`)
- **`SpatialConstraint`**: bounds-checked latitude, longitude, and positive radius
- **`TimeWindow`**: typed datetime fields with optional `last_n_hours > 0`
- **Extra fields**: Pydantic v2 default behavior ignores unknown fields (no injection of unexpected parameters)

---

## 3. SQL Safety

The structured retriever (`dynatrust_rag/retrieval/structured.py`) and spatial retriever (`dynatrust_rag/retrieval/spatial.py`) use `asyncpg`'s parameterized query interface exclusively:

```python
# Example from spatial retriever
rows = await conn.fetch(
    """SELECT id, name, ST_Distance(geom::geography, ST_MakePoint($1, $2)::geography) as distance
       FROM assets WHERE ST_DWithin(geom::geography, ST_MakePoint($1, $2)::geography, $3)""",
    longitude, latitude, radius_meters,
)
```

No user-supplied strings are interpolated into SQL. The `text-to-SQL` path (structured retriever) uses predefined query templates with parameter substitution, not LLM-generated SQL.

---

## 4. Provenance and Auditability

Every query response can include a `Provenance` object containing:

- **`steps`**: ordered list of retrieval actions (type, tables accessed, chunk IDs, similarity scores)
- **`sql_executed`**: exact SQL queries run (for reproducibility)
- **`row_references`**: specific database rows (table + primary key) that contributed to the answer
- **`source_docs`**: document identifiers for semantic chunks used

This enables:
- Post-hoc attribution auditing (did the answer come from the cited sources?)
- Reproducibility (re-run the same SQL and vector queries)
- Tamper detection (compare `content_hash` of chunks against stored values)

---

## 5. Staleness Detection

The `StalenessTracker` compares the vector index refresh timestamp against the newest data modification timestamp in the `vector_index_metadata` table. When lag exceeds a configurable threshold:

1. The response includes `staleness_info.staleness_detected = true` with the lag in seconds
2. The LLM prompt includes a freshness warning, instructing the model to prefer structured/spatial results
3. Downstream consumers can use `staleness_info` to decide whether to trust semantic results

---

## 6. LLM Output Validation

The `OutputSchemaValidator` (`dynatrust_rag/validation/output_schema.py`) provides basic structural validation of LLM-generated answers:

- **Entity grounding check**: verifies that entity identifiers in the answer appear in the provenance chain
- **Length bounds**: rejects suspiciously short or excessively long outputs
- **Format validation**: checks for required sections or patterns when structured output is expected

This is a lightweight first step toward the schema-level constraint enforcement described in the PrivRAG research proposal.

---

## 7. CORS and Network

- CORS origins are configurable via `DYNATRUST_CORS_ORIGINS` (defaults to `http://localhost:3000`; never `*` in production)
- Allowed methods restricted to `GET` and `POST`
- Allowed headers restricted to `Content-Type` and `Authorization`

---

## 8. Secrets Management

- API keys (`OPENAI_API_KEY`, `GEMINI_API_KEY`) are loaded from environment variables, never hardcoded
- `.env.example` contains only placeholder values
- `.gitignore` excludes `.env` files
- The repository history previously contained a real API key (commit `5ebc4f6`); it has been rotated

---

## 9. Known Limitations

- **No authentication/authorization** on the API endpoint (suitable for local/research use only)
- **No rate limiting** (add via reverse proxy for any shared deployment)
- **Query logging** (`QueryLogger`) writes to the database without encryption; logs may contain PII from user questions
- **Provenance is append-only** but not cryptographically signed (no Merkle chain or hash linking between steps)
- **Attribution metrics** use heuristic entity extraction, not verified NER
- **LLM output validation** is structural only; semantic correctness requires human evaluation or reference-based metrics

---

## 10. Research Extensions (PrivRAG)

The PrivRAG research proposal builds on this security model with three additional defense layers:

1. **Trust-stratified retrieval**: assign trust scores to corpus segments; weight retrieval by source trustworthiness
2. **Privilege-separated generation**: run retrieval and generation in isolated contexts with minimal authority
3. **Schema-level constraint enforcement**: validate LLM outputs against database schema constraints before returning to users

These extensions are the subject of ongoing research and are not yet implemented in the current prototype.
