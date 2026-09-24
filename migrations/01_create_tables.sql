CREATE TABLE vessels (
  id                 BIGSERIAL PRIMARY KEY,
  mmsi               BIGINT NOT NULL UNIQUE,    -- Maritime Mobile Service Identity
  imo                TEXT,                      -- IMO number (sometimes missing)
  callsign           TEXT,
  name               TEXT,
  ship_type          TEXT,                      -- AIS ship type text/code
  cargo_type         TEXT,
  width_m            DOUBLE PRECISION,          -- static dimension estimates (meters)
  length_m           DOUBLE PRECISION,
  position_fixing_device_type TEXT,
  last_known_draught_m DOUBLE PRECISION,        -- optional: last reported draught (meters)
  first_seen_at      TIMESTAMPTZ DEFAULT now(),
  last_seen_at       TIMESTAMPTZ
);


CREATE TABLE ais_positions (
  id                       BIGSERIAL,
  timestamp                TIMESTAMPTZ NOT NULL,     -- parsed from CSV (DD/MM/YYYY HH24:MI:SS)
  type_of_mobile           TEXT,
  mmsi                     BIGINT NOT NULL,
  latitude                 DOUBLE PRECISION,
  longitude                DOUBLE PRECISION,
  navigational_status      TEXT,
  rate_of_turn             DOUBLE PRECISION,
  speed_over_ground        DOUBLE PRECISION,
  course_over_ground       DOUBLE PRECISION,
  heading                  INTEGER,
  imo                      TEXT,
  callsign                 TEXT,
  name                     TEXT,
  ship_type                TEXT,
  cargo_type               TEXT,
  width_m                  DOUBLE PRECISION,
  length_m                 DOUBLE PRECISION,
  position_fixing_device_type TEXT,
  draught_m                DOUBLE PRECISION,       -- draught at time of this AIS message (meters)
  destination              TEXT,
  eta                      TIMESTAMPTZ,            -- ETA if available (store as timestamptz if full date+time)
  data_source_type         TEXT,
  size_a_m                 DOUBLE PRECISION,
  size_b_m                 DOUBLE PRECISION,
  size_c_m                 DOUBLE PRECISION,
  size_d_m                 DOUBLE PRECISION,
  position_geog            geography(Point,4326),  -- spatial column (lat/lon) as geography
  raw_payload              JSONB,                  -- optional: keep original row/extra fields
  created_at               TIMESTAMPTZ DEFAULT now()
);

SELECT create_hypertable('ais_positions', 'timestamp', chunk_time_interval => INTERVAL '1 day');
