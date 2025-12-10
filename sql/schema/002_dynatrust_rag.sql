-- DynaTrust-RAG Schema Initialization
-- Version: 0.1.0
--
-- This schema extends the Atlas4D base with tables specific to the
-- DynaTrust-RAG research prototype:
-- - Document chunks with vector embeddings for semantic search
-- - Vector index metadata for staleness tracking  
-- - Query/answer logging for evaluation
-- - Gold labels for accuracy assessment

-- Create DynaTrust schema
CREATE SCHEMA IF NOT EXISTS dynatrust;

-- Grant permissions
GRANT ALL ON SCHEMA dynatrust TO atlas4d_app;

-- =============================================================================
-- Document Chunks Table
-- Stores chunked documents with vector embeddings for semantic retrieval
-- =============================================================================

CREATE TABLE IF NOT EXISTS dynatrust.document_chunks (
    id              SERIAL PRIMARY KEY,
    doc_id          TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    source_type     TEXT DEFAULT 'documentation',
    metadata        JSONB DEFAULT '{}',
    embedding       VECTOR(768),  -- Dimension matches common embedding models
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    
    -- Ensure unique chunks per document
    CONSTRAINT unique_doc_chunk UNIQUE (doc_id, chunk_index)
);

-- Indexes for document chunks
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id 
    ON dynatrust.document_chunks (doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_source_type 
    ON dynatrust.document_chunks (source_type);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding 
    ON dynatrust.document_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Comment on table
COMMENT ON TABLE dynatrust.document_chunks IS 
    'Chunked documents with vector embeddings for semantic retrieval in DynaTrust-RAG';


-- =============================================================================
-- Vector Index Metadata Table
-- Tracks freshness of vector indices for staleness-aware retrieval
-- =============================================================================

CREATE TABLE IF NOT EXISTS dynatrust.vector_index_metadata (
    index_name      TEXT PRIMARY KEY,
    last_refresh_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    chunk_count     INTEGER DEFAULT 0,
    embedding_model TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Comment on table
COMMENT ON TABLE dynatrust.vector_index_metadata IS
    'Tracks vector index refresh times for staleness detection';

-- Insert default entry for document chunks
INSERT INTO dynatrust.vector_index_metadata (index_name, chunk_count, embedding_model)
VALUES ('document_chunks', 0, 'default')
ON CONFLICT (index_name) DO NOTHING;


-- =============================================================================
-- Query Logging Table
-- Stores all queries for evaluation and replay
-- =============================================================================

CREATE TABLE IF NOT EXISTS dynatrust.queries (
    id              SERIAL,
    query_id        TEXT PRIMARY KEY,
    question        TEXT NOT NULL,
    request_json    JSONB,
    session_id      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for queries
CREATE INDEX IF NOT EXISTS idx_queries_session 
    ON dynatrust.queries (session_id);
CREATE INDEX IF NOT EXISTS idx_queries_created 
    ON dynatrust.queries (created_at DESC);

-- Comment on table
COMMENT ON TABLE dynatrust.queries IS
    'Logged queries for evaluation and replay in DynaTrust-RAG';


-- =============================================================================
-- Answer Logging Table
-- Stores generated answers with provenance for evaluation
-- =============================================================================

CREATE TABLE IF NOT EXISTS dynatrust.answers (
    id                  SERIAL,
    query_id            TEXT PRIMARY KEY REFERENCES dynatrust.queries(query_id),
    answer              TEXT NOT NULL,
    provenance_json     JSONB,
    staleness_json      JSONB,
    query_type          TEXT,
    processing_time_ms  DOUBLE PRECISION,
    confidence_score    DOUBLE PRECISION,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for answers
CREATE INDEX IF NOT EXISTS idx_answers_query_type 
    ON dynatrust.answers (query_type);
CREATE INDEX IF NOT EXISTS idx_answers_created 
    ON dynatrust.answers (created_at DESC);

-- Comment on table
COMMENT ON TABLE dynatrust.answers IS
    'Generated answers with provenance for evaluation';


-- =============================================================================
-- Gold Labels Table
-- Stores ground truth labels for evaluation experiments
-- =============================================================================

CREATE TABLE IF NOT EXISTS dynatrust.gold_labels (
    id              SERIAL,
    query_id        TEXT PRIMARY KEY REFERENCES dynatrust.queries(query_id),
    gold_answer     TEXT NOT NULL,
    rating          INTEGER CHECK (rating BETWEEN 1 AND 5),
    notes           TEXT,
    annotator       TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for gold labels
CREATE INDEX IF NOT EXISTS idx_gold_labels_annotator 
    ON dynatrust.gold_labels (annotator);
CREATE INDEX IF NOT EXISTS idx_gold_labels_rating 
    ON dynatrust.gold_labels (rating);

-- Comment on table
COMMENT ON TABLE dynatrust.gold_labels IS
    'Ground truth labels for evaluation experiments';


-- =============================================================================
-- Evaluation Metrics Table
-- Stores computed metrics from evaluation runs
-- =============================================================================

CREATE TABLE IF NOT EXISTS dynatrust.evaluation_runs (
    id                  SERIAL PRIMARY KEY,
    run_id              TEXT UNIQUE NOT NULL,
    run_name            TEXT,
    num_samples         INTEGER,
    mean_coverage       DOUBLE PRECISION,
    mean_utilization    DOUBLE PRECISION,
    hallucination_rate  DOUBLE PRECISION,
    accuracy            DOUBLE PRECISION,
    config_json         JSONB,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Comment on table
COMMENT ON TABLE dynatrust.evaluation_runs IS
    'Results from evaluation experiments';


-- =============================================================================
-- Staleness Simulation Table
-- For experiments on staleness robustness
-- =============================================================================

CREATE TABLE IF NOT EXISTS dynatrust.staleness_experiments (
    id                  SERIAL PRIMARY KEY,
    experiment_id       TEXT UNIQUE NOT NULL,
    simulated_lag_seconds INTEGER NOT NULL,
    num_queries         INTEGER,
    accuracy_with_semantic    DOUBLE PRECISION,
    accuracy_without_semantic DOUBLE PRECISION,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Comment on table
COMMENT ON TABLE dynatrust.staleness_experiments IS
    'Results from staleness robustness experiments';


-- =============================================================================
-- Assets Table
-- Stores structured data about assets for StructuredRetriever queries
-- =============================================================================

CREATE TABLE IF NOT EXISTS dynatrust.assets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    asset_type      TEXT NOT NULL DEFAULT 'equipment',
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'decommissioned')),
    install_date    DATE,
    location        TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for assets
CREATE INDEX IF NOT EXISTS idx_assets_status ON dynatrust.assets (status);
CREATE INDEX IF NOT EXISTS idx_assets_install_date ON dynatrust.assets (install_date);
CREATE INDEX IF NOT EXISTS idx_assets_type ON dynatrust.assets (asset_type);

-- Comment on table
COMMENT ON TABLE dynatrust.assets IS
    'Structured asset data for StructuredRetriever queries (install dates, status filters)';


-- =============================================================================
-- Spatial Points Table
-- Stores spatial data for SpatialRetriever PostGIS queries
-- =============================================================================

CREATE TABLE IF NOT EXISTS dynatrust.spatial_points (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    point_type      TEXT DEFAULT 'poi',
    geom            GEOMETRY(POINT, 4326) NOT NULL,
    description     TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Spatial index on geometry
CREATE INDEX IF NOT EXISTS idx_spatial_points_geom 
    ON dynatrust.spatial_points USING GIST (geom);

-- Comment on table
COMMENT ON TABLE dynatrust.spatial_points IS
    'Spatial points for SpatialRetriever PostGIS queries (ST_DWithin searches)';


-- =============================================================================
-- Grant permissions on all new tables
-- =============================================================================

GRANT ALL ON ALL TABLES IN SCHEMA dynatrust TO atlas4d_app;
GRANT ALL ON ALL SEQUENCES IN SCHEMA dynatrust TO atlas4d_app;


-- =============================================================================
-- Success message
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE 'DynaTrust-RAG schema initialized successfully';
END $$;
