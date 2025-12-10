-- Atlas4D Base Demo Data: Telecom Network Scenario
-- Simple but believable network topology demo

-- Ensure schema exists
CREATE SCHEMA IF NOT EXISTS atlas4d;

-- Network Nodes: OLTs, Switches, CPE devices
-- Centered around Burgas with realistic network topology

-- OLT locations (Central offices)
INSERT INTO atlas4d.observations_core (t, lat, lon, geom, source_type, track_id, speed_ms, metadata)
VALUES 
    (NOW() - INTERVAL '1 hour', 42.5048, 27.4626, ST_SetSRID(ST_MakePoint(27.4626, 42.5048), 4326), 'olt', gen_random_uuid(), 0, '{"name": "OLT-Burgas-Central", "type": "olt", "capacity_gbps": 40, "active_ports": 128}'),
    (NOW() - INTERVAL '1 hour', 42.4892, 27.4734, ST_SetSRID(ST_MakePoint(27.4734, 42.4892), 4326), 'olt', gen_random_uuid(), 0, '{"name": "OLT-Burgas-South", "type": "olt", "capacity_gbps": 40, "active_ports": 96}'),
    (NOW() - INTERVAL '1 hour', 42.5234, 27.4412, ST_SetSRID(ST_MakePoint(27.4412, 42.5234), 4326), 'olt', gen_random_uuid(), 0, '{"name": "OLT-Burgas-North", "type": "olt", "capacity_gbps": 20, "active_ports": 64}');

-- Distribution switches
INSERT INTO atlas4d.observations_core (t, lat, lon, geom, source_type, track_id, speed_ms, metadata)
SELECT 
    NOW() - (random() * INTERVAL '2 hours'),
    42.5 + (random() - 0.5) * 0.05,
    27.46 + (random() - 0.5) * 0.08,
    ST_SetSRID(ST_MakePoint(27.46 + (random() - 0.5) * 0.08, 42.5 + (random() - 0.5) * 0.05), 4326),
    'switch',
    gen_random_uuid(),
    0,
    jsonb_build_object(
        'name', 'SW-' || lpad((row_number() OVER())::text, 3, '0'),
        'type', 'distribution_switch',
        'uplink_gbps', (ARRAY[1, 10, 10, 10])[ceil(random()*4)],
        'ports_used', floor(random() * 24 + 1)
    )
FROM generate_series(1, 5);

-- CPE devices (customer endpoints)
INSERT INTO atlas4d.observations_core (t, lat, lon, geom, source_type, track_id, speed_ms, heading_deg, metadata)
SELECT 
    NOW() - (random() * INTERVAL '4 hours'),
    42.5 + (random() - 0.5) * 0.08,
    27.46 + (random() - 0.5) * 0.12,
    ST_SetSRID(ST_MakePoint(27.46 + (random() - 0.5) * 0.12, 42.5 + (random() - 0.5) * 0.08), 4326),
    'cpe',
    gen_random_uuid(),
    0,
    0,
    jsonb_build_object(
        'name', 'CPE-' || lpad((row_number() OVER())::text, 4, '0'),
        'type', 'ont',
        'rx_power_dbm', round((random() * 8 - 28)::numeric, 1),
        'tx_power_dbm', round((random() * 3 + 2)::numeric, 1),
        'bandwidth_mbps', (ARRAY[100, 200, 500, 1000])[ceil(random()*4)]
    )
FROM generate_series(1, 20);

-- Traffic metrics (time-series observations)
INSERT INTO atlas4d.observations_core (t, lat, lon, geom, source_type, track_id, speed_ms, metadata)
SELECT 
    NOW() - (gs * INTERVAL '5 minutes'),
    42.5048, 27.4626,
    ST_SetSRID(ST_MakePoint(27.4626, 42.5048), 4326),
    'traffic_metric',
    '11111111-1111-1111-1111-111111111111'::uuid,
    round((random() * 30 + 10)::numeric, 2),  -- bandwidth utilization %
    jsonb_build_object(
        'metric_type', 'bandwidth',
        'node', 'OLT-Burgas-Central',
        'throughput_gbps', round((random() * 20 + 5)::numeric, 2),
        'latency_ms', round((random() * 5 + 1)::numeric, 1),
        'packet_loss_pct', round((random() * 0.5)::numeric, 3)
    )
FROM generate_series(1, 50) gs;

-- Network anomalies
INSERT INTO atlas4d.anomalies (observation_id, anomaly_type, severity, score, detected_at, metadata)
SELECT 
    id,
    (ARRAY['high_latency', 'packet_loss', 'link_down', 'congestion', 'power_warning'])[ceil(random()*5)],
    ceil(random() * 4 + 1)::int,
    random(),
    NOW() - (random() * INTERVAL '6 hours'),
    jsonb_build_object(
        'network_demo', true,
        'affected_customers', floor(random() * 50 + 1),
        'duration_minutes', floor(random() * 30 + 5)
    )
FROM atlas4d.observations_core
WHERE source_type IN ('olt', 'switch', 'cpe')
AND random() < 0.3
LIMIT 15;

-- Verify
DO $$
DECLARE
    obs_count INT;
    anom_count INT;
    node_types TEXT;
BEGIN
    SELECT COUNT(*) INTO obs_count FROM atlas4d.observations_core 
    WHERE source_type IN ('olt', 'switch', 'cpe', 'traffic_metric');
    
    SELECT COUNT(*) INTO anom_count FROM atlas4d.anomalies 
    WHERE metadata->>'network_demo' = 'true';
    
    SELECT string_agg(DISTINCT source_type, ', ') INTO node_types 
    FROM atlas4d.observations_core 
    WHERE source_type IN ('olt', 'switch', 'cpe', 'traffic_metric');
    
    RAISE NOTICE 'Telecom demo loaded: % network observations, % anomalies', obs_count, anom_count;
    RAISE NOTICE 'Node types: %', node_types;
END $$;
