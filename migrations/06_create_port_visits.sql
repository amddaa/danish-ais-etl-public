CREATE TABLE IF NOT EXISTS port_visits (
    id BIGSERIAL PRIMARY KEY,
    mmsi BIGINT NOT NULL REFERENCES vessels(mmsi),
    port_id INTEGER NOT NULL REFERENCES ports(id),
    arrival_time TIMESTAMPTZ NOT NULL,
    departure_time TIMESTAMPTZ,
    stay_duration_hours DOUBLE PRECISION GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (departure_time - arrival_time)) / 3600.0
    ) STORED,
    -- Vessel parameters during the visit
    draught_m DOUBLE PRECISION,          -- median draught calculated from port positions
    ship_type TEXT,
    cargo_type TEXT,
    length_m DOUBLE PRECISION,
    width_m DOUBLE PRECISION,
    -- Destination declared BEFORE entering the port
    declared_destination TEXT,            -- last AIS destination reported prior to arrival
    -- Metadata
    n_positions INTEGER,                 -- number of AIS signals received during the visit
    created_at TIMESTAMPTZ DEFAULT now(),
    -- Constraint preventing duplicates during re-runs
    UNIQUE (mmsi, port_id, arrival_time)
);

CREATE INDEX IF NOT EXISTS idx_port_visits_mmsi ON port_visits(mmsi);
CREATE INDEX IF NOT EXISTS idx_port_visits_port ON port_visits(port_id);
CREATE INDEX IF NOT EXISTS idx_port_visits_arrival ON port_visits(arrival_time);
CREATE INDEX IF NOT EXISTS idx_port_visits_ship_type ON port_visits(ship_type);

COMMENT ON TABLE port_visits IS 'Port visits detected by the AIS State Machine. Each row represents a single continuous vessels stay at a port.';
