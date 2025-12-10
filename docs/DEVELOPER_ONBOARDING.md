# Developer Onboarding Guide

Welcome to Atlas4D Base! This guide will help you understand the architecture and start contributing in under 30 minutes.

---

## 🎯 First 10 Minutes

### 1. Start the Stack (2 min)
```bash
git clone https://github.com/crisbez/atlas4d-base.git
cd atlas4d-base
docker compose up -d
```

### 2. Load Demo Data (1 min)
```bash
docker compose exec postgres psql -U atlas4d_app -d atlas4d \
  -f /docker-entrypoint-initdb.d/seed/demo_burgas.sql
```

### 3. Explore the API (2 min)
```bash
# Health
curl http://localhost:8090/health | jq

# Stats
curl http://localhost:8090/api/stats | jq

# Observations
curl "http://localhost:8090/api/observations?limit=5" | jq

# GeoJSON
curl "http://localhost:8090/api/geojson/observations?limit=10" | jq
```

### 4. Open the Map (1 min)

Visit http://localhost:8091 and explore the Burgas demo.

### 5. Read the Schema (4 min)
```bash
cat sql/schema/001_init.sql
```

Key tables:
- `atlas4d.observations_core` - Main spatiotemporal data (TimescaleDB hypertable)
- `atlas4d.anomalies` - Detected anomalies
- `atlas4d.trajectory_embeddings` - ML embeddings (pgvector)

---

## 🏗️ Architecture Overview
```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (:8091)                      │
│                   Leaflet + nginx reverse proxy              │
└─────────────────────────┬───────────────────────────────────┘
                          │ /api/* proxied to
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     API Gateway (:8090)                      │
│                FastAPI + asyncpg + redis                     │
│                                                              │
│  Endpoints:                                                  │
│  - GET  /health              Health check                    │
│  - GET  /api/stats           Platform statistics             │
│  - GET  /api/observations    Query observations              │
│  - POST /api/observations    Create observation              │
│  - GET  /api/anomalies       Query anomalies                 │
│  - GET  /api/geojson/*       Map-ready GeoJSON               │
└──────────┬─────────────────────────────┬────────────────────┘
           │                             │
           ▼                             ▼
┌─────────────────────┐       ┌─────────────────────┐
│   PostgreSQL (:5433) │       │    Redis (:6380)    │
│                     │       │                     │
│ Extensions:         │       │ Used for:           │
│ - PostGIS (geo)     │       │ - Session cache     │
│ - TimescaleDB (ts)  │       │ - Rate limiting     │
│ - pgvector (ML)     │       │                     │
└─────────────────────┘       └─────────────────────┘
```

---

## 📊 Database Schema

### observations_core (Main Table)
```sql
CREATE TABLE atlas4d.observations_core (
    id              BIGSERIAL,
    t               TIMESTAMPTZ NOT NULL,    -- Time (partition key)
    geom            GEOMETRY(Point, 4326),   -- Location (PostGIS)
    source_type     TEXT,                    -- vehicle, sensor, camera, olt, etc.
    track_id        UUID,                    -- For trajectory grouping
    lat/lon         DOUBLE PRECISION,        -- Convenience columns
    speed_ms        DOUBLE PRECISION,
    heading_deg     DOUBLE PRECISION,
    metadata        JSONB,                   -- Flexible attributes
    PRIMARY KEY (id, t)                      -- Composite for TimescaleDB
);

-- Automatically partitioned by time (1 day chunks)
SELECT create_hypertable('observations_core', 't');
```

### Key Indexes
```sql
-- Spatial queries
CREATE INDEX idx_obs_geom ON observations_core USING GIST (geom);

-- Filter by source
CREATE INDEX idx_obs_source ON observations_core (source_type);

-- Track trajectories
CREATE INDEX idx_obs_track ON observations_core (track_id);
```

---

## 🛠️ Common Tasks

### Add a New Endpoint
```python
# services/api-gateway/main.py

@app.get("/api/trajectories/{track_id}")
async def get_trajectory(track_id: str):
    """Get all points for a trajectory"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, t, lat, lon, speed_ms
            FROM atlas4d.observations_core
            WHERE track_id = $1
            ORDER BY t
        """, track_id)
        return [dict(row) for row in rows]
```

### Add a New Source Type

Just insert with a new `source_type`:
```sql
INSERT INTO atlas4d.observations_core (t, lat, lon, geom, source_type, metadata)
VALUES (
    NOW(),
    42.5, 27.46,
    ST_SetSRID(ST_MakePoint(27.46, 42.5), 4326),
    'drone',  -- New source type
    '{"altitude_m": 100, "battery_pct": 85}'
);
```

The frontend will show it with the default color. To add a custom color, edit `services/frontend/index.html`:
```javascript
const sourceColors = {
    'vehicle': '#3498db',
    'sensor': '#2ecc71',
    'drone': '#9b59b6',  // Add your color
    // ...
};
```

### Run a Spatial Query
```sql
-- Find observations within 5km of Burgas center
SELECT id, t, source_type, 
       ST_Distance(geom::geography, 
                   ST_SetSRID(ST_MakePoint(27.4626, 42.5048), 4326)::geography) / 1000 as dist_km
FROM atlas4d.observations_core
WHERE ST_DWithin(
    geom::geography,
    ST_SetSRID(ST_MakePoint(27.4626, 42.5048), 4326)::geography,
    5000  -- 5km in meters
)
ORDER BY t DESC
LIMIT 20;
```

### Run a Time-Series Query
```sql
-- Observations per hour for the last 24 hours
SELECT 
    time_bucket('1 hour', t) as hour,
    source_type,
    COUNT(*) as count
FROM atlas4d.observations_core
WHERE t > NOW() - INTERVAL '24 hours'
GROUP BY hour, source_type
ORDER BY hour;
```

---

## 🧪 Testing Your Changes

### Quick Smoke Test
```bash
# 1. Stack health
curl -s http://localhost:8090/health | jq '.status'

# 2. Data exists
curl -s http://localhost:8090/api/stats | jq '.total_observations > 0'

# 3. Your endpoint works
curl -s http://localhost:8090/api/your-endpoint | jq
```

### Connect to Database Directly
```bash
docker compose exec postgres psql -U atlas4d_app -d atlas4d

# Useful commands:
\dt atlas4d.*           -- List tables
\d atlas4d.observations_core  -- Describe table
SELECT COUNT(*) FROM atlas4d.observations_core;
```

### View Logs
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api-gateway
```

---

## 📚 Further Reading

- [Quick Start Guide](quickstart/QUICK_START.md)
- [API Reference](api/API_REFERENCE.md)
- [Database Schema](architecture/SCHEMA.md)
- [Architecture Overview](architecture/ARCHITECTURE.md)

---

## 🤝 Ready to Contribute?

1. Pick an issue or create one
2. Fork the repo
3. Make your changes
4. Run smoke tests
5. Submit a PR

See [CONTRIBUTING.md](../CONTRIBUTING.md) for detailed guidelines.

---

**Questions?** Open an issue or email office@atlas4d.tech
