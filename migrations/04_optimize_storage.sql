-- 1. DROP REDUNDANT INDEX
-- We have a UNIQUE INDEX (mmsi, timestamp) which covers the same queries as (mmsi, timestamp DESC).
-- The DESC index is redundant and doubles the storage for this pattern.
-- Note: 'ais_positions_mmsi_timestamp_idx1' is a guessed name for the second index created in 02_add_indexes_constr.sql.
-- If this fails, check the index name in pgAdmin (likely ends in _idx1 or similar).
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (SELECT indexname FROM pg_indexes WHERE tablename = 'ais_positions' AND indexdef LIKE '%(mmsi, "timestamp" DESC)%') LOOP
        EXECUTE 'DROP INDEX IF EXISTS ' || quote_ident(r.indexname);
    END LOOP;
END $$;


-- 2. ENABLE TIMESCALEDB COMPRESSION
-- This converts row-based chunks into columnar compressed chunks for older data.
-- Savings are typically 90-95%.

-- Enable compression on the hypertable
ALTER TABLE ais_positions SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'mmsi',  -- Segment by vessel for fast per-vessel lookups
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- 3. ADD COMPRESSION POLICY
-- Automatically compress chunks that are older than 3 days.
-- We keep 3 days uncompressed to allow fast heavy inserts and updates.
SELECT add_compression_policy('ais_positions', INTERVAL '3 days');
