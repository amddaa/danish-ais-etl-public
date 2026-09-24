-- Spatial index for nearest/bounding-box/distance queries
CREATE INDEX ON ais_positions USING GIST (position_geog);

-- Frequent access pattern: per-vessel recent positions
CREATE INDEX ON ais_positions (mmsi, timestamp DESC);

-- Fast time-range scans (useful if chunking is large)
CREATE INDEX ON ais_positions USING BRIN (timestamp);

CREATE UNIQUE INDEX ON ais_positions (mmsi, timestamp);