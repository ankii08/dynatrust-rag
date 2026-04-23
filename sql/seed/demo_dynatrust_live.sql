-- DynaTrust-RAG live demo data for StructuredRetriever and SpatialRetriever
-- Idempotent: removes prior rows created by this script before reinserting.

-- -----------------------------------------------------------------------------
-- Structured demo data
-- -----------------------------------------------------------------------------

DELETE FROM dynatrust.assets
WHERE metadata->>'demo_seed' = 'live_demo';

INSERT INTO dynatrust.assets
    (id, name, asset_type, status, install_date, location, metadata)
VALUES
    (
        '11111111-1111-1111-1111-111111111111',
        'BG-OLT-PORT-01',
        'olt',
        'active',
        DATE '2023-02-14',
        'Burgas Port',
        jsonb_build_object(
            'demo_seed', 'live_demo',
            'notes', 'Primary optical line terminal serving Burgas Port logistics zone'
        )
    ),
    (
        '22222222-2222-2222-2222-222222222222',
        'BG-SW-CENTRAL-02',
        'distribution_switch',
        'active',
        DATE '2024-06-09',
        'Burgas Central',
        jsonb_build_object(
            'demo_seed', 'live_demo',
            'notes', 'Core switch for downtown aggregation traffic'
        )
    ),
    (
        '33333333-3333-3333-3333-333333333333',
        'BG-CPE-SOUTH-15',
        'cpe',
        'inactive',
        DATE '2021-11-03',
        'Burgas South',
        jsonb_build_object(
            'demo_seed', 'live_demo',
            'notes', 'Customer edge device awaiting replacement'
        )
    ),
    (
        '44444444-4444-4444-4444-444444444444',
        'BG-RADIO-NORTH-07',
        'radio_node',
        'active',
        DATE '2022-09-21',
        'Burgas North',
        jsonb_build_object(
            'demo_seed', 'live_demo',
            'notes', 'Backhaul radio node feeding northern access sites'
        )
    ),
    (
        '55555555-5555-5555-5555-555555555555',
        'BG-LEGACY-CAB-03',
        'street_cabinet',
        'decommissioned',
        DATE '2019-04-18',
        'Burgas East',
        jsonb_build_object(
            'demo_seed', 'live_demo',
            'notes', 'Legacy cabinet retired after fiber refresh'
        )
    );

-- -----------------------------------------------------------------------------
-- Spatial demo data
-- -----------------------------------------------------------------------------

DELETE FROM dynatrust.spatial_points
WHERE metadata->>'demo_seed' = 'live_demo';

INSERT INTO dynatrust.spatial_points
    (id, name, point_type, geom, description, metadata)
VALUES
    (
        'aaaaaaa1-aaaa-aaaa-aaaa-aaaaaaaaaaa1',
        'Burgas Port Fiber Hub',
        'telecom_site',
        ST_SetSRID(ST_MakePoint(27.4678, 42.4926), 4326),
        'Fiber aggregation hub serving the port and nearby logistics terminals.',
        jsonb_build_object(
            'demo_seed', 'live_demo',
            'city', 'Burgas',
            'zone', 'port',
            'service', 'fiber_backhaul'
        )
    ),
    (
        'aaaaaaa2-aaaa-aaaa-aaaa-aaaaaaaaaaa2',
        'Burgas Port Cell Tower',
        'cell_tower',
        ST_SetSRID(ST_MakePoint(27.4694, 42.4941), 4326),
        'Macro cell site covering port traffic and waterfront operations.',
        jsonb_build_object(
            'demo_seed', 'live_demo',
            'city', 'Burgas',
            'zone', 'port',
            'service', 'lte'
        )
    ),
    (
        'aaaaaaa3-aaaa-aaaa-aaaa-aaaaaaaaaaa3',
        'Burgas Downtown Exchange',
        'exchange',
        ST_SetSRID(ST_MakePoint(27.4731, 42.5015), 4326),
        'Downtown telecom exchange connected to the metro fiber ring.',
        jsonb_build_object(
            'demo_seed', 'live_demo',
            'city', 'Burgas',
            'zone', 'central',
            'service', 'exchange'
        )
    ),
    (
        'aaaaaaa4-aaaa-aaaa-aaaa-aaaaaaaaaaa4',
        'Burgas South Relay',
        'relay',
        ST_SetSRID(ST_MakePoint(27.4582, 42.4864), 4326),
        'Relay point supporting southern neighborhood coverage.',
        jsonb_build_object(
            'demo_seed', 'live_demo',
            'city', 'Burgas',
            'zone', 'south',
            'service', 'microwave'
        )
    ),
    (
        'aaaaaaa5-aaaa-aaaa-aaaa-aaaaaaaaaaa5',
        'Aytos Regional Tower',
        'cell_tower',
        ST_SetSRID(ST_MakePoint(27.2550, 42.7044), 4326),
        'Regional tower outside the Burgas urban area used as a far-away control point.',
        jsonb_build_object(
            'demo_seed', 'live_demo',
            'city', 'Aytos',
            'zone', 'regional',
            'service', 'lte'
        )
    );

DO $$
DECLARE
    asset_count INT;
    point_count INT;
BEGIN
    SELECT COUNT(*) INTO asset_count
    FROM dynatrust.assets
    WHERE metadata->>'demo_seed' = 'live_demo';

    SELECT COUNT(*) INTO point_count
    FROM dynatrust.spatial_points
    WHERE metadata->>'demo_seed' = 'live_demo';

    RAISE NOTICE 'Loaded % demo assets and % demo spatial points for DynaTrust live demo.',
        asset_count, point_count;
END $$;
