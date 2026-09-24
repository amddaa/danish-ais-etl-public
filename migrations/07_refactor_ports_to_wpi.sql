-- Migration 07: Refactor `ports` table to WPI hierarchy
-- Changes:
--   1. Rename existing `ports` (terminals/quays) to `port_terminals`.
--   2. Add `port_id` FK on `port_terminals` pointing to the new `ports` table.
--   3. Create new `ports` table with full WPI (Pub 150) schema.
--   4. Fix FK on `port_visits` to remain valid (it already points to port_terminals.id).
-- Run with: psql -d <db> -f 07_refactor_ports_to_wpi.sql

BEGIN;

-- Step 1: Rename existing `ports` table -> `port_terminals` (ONLY if not already done)
--         We check if 'ports' table has old schema (lacks 'wpi_number' column)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'ports') 
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'ports' AND column_name = 'wpi_number')
    THEN
        -- This is the OLD quays table, rename it
        ALTER TABLE ports RENAME TO port_terminals;
        
        -- Conditional rename of constraint (Postgres doesn't support IF EXISTS for RENAME)
        IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ports_pkey' AND conrelid = 'port_terminals'::regclass) THEN
            ALTER TABLE port_terminals RENAME CONSTRAINT ports_pkey TO port_terminals_pkey;
        END IF;

        DROP INDEX IF EXISTS ports_geom_idx;
        CREATE INDEX IF NOT EXISTS idx_port_terminals_geom ON port_terminals USING GIST (geom);
    END IF;
END;
$$;

COMMENT ON TABLE port_terminals IS
    'Physical terminals / quays sourced from OpenStreetMap or similar. '
    'Each terminal belongs to a WPI Port via port_id FK.';

-- Step 2: Add parent WPI port reference (filled by spatial_link_wpi.py later)
ALTER TABLE port_terminals
    ADD COLUMN IF NOT EXISTS port_id INTEGER; -- FK added after ports table exists

-- Step 3: Create new WPI-based `ports` table
CREATE TABLE IF NOT EXISTS ports (
    id                              SERIAL PRIMARY KEY,
    wpi_number                      INTEGER UNIQUE,        -- World Port Index Number
    name                            TEXT NOT NULL,         -- Main Port Name
    name_alternate                  TEXT,                  -- Alternate Port Name
    un_locode                       TEXT,            -- UN/LOCODE (up to 7 chars in WPI)
    country_code                    TEXT,             -- WPI stores full country name, not ISO-2
    region_name                     TEXT,                  -- WPI Region Name

    geom                            geography(Point, 4326), -- WGS-84 point geometry
    world_water_body                TEXT,                  -- e.g. "Baltic Sea"
    iho_sea_area                    TEXT,                  -- IHO S-130 Sea Area

    tidal_range_m                   DOUBLE PRECISION,
    entrance_width_m                DOUBLE PRECISION,
    channel_depth_m                 DOUBLE PRECISION,
    anchorage_depth_m               DOUBLE PRECISION,
    cargo_pier_depth_m              DOUBLE PRECISION,
    oil_terminal_depth_m            DOUBLE PRECISION,
    lng_terminal_depth_m            DOUBLE PRECISION,      -- Liquified Natural Gas Terminal Depth
    max_vessel_length_m             DOUBLE PRECISION,
    max_vessel_beam_m               DOUBLE PRECISION,
    max_vessel_draft_m              DOUBLE PRECISION,      -- Critical for draught validation
    offshore_max_vessel_length_m    DOUBLE PRECISION,
    offshore_max_vessel_beam_m      DOUBLE PRECISION,
    offshore_max_vessel_draft_m     DOUBLE PRECISION,

    harbor_size                     TEXT,                  -- Very Small / Small / Medium / Large
    harbor_type                     TEXT,                  -- Coastal (Natural), River Tide, etc.
    harbor_use                      TEXT,                  -- Public / Private / Military / etc.
    shelter_afforded                TEXT,                  -- Good / Fair / Poor / None

    restriction_tide                TEXT,
    restriction_heavy_swell         TEXT,
    restriction_ice                 TEXT,
    restriction_other               TEXT,

    overhead_limits                 TEXT,
    underkeel_clearance_system      TEXT,
    good_holding_ground             TEXT,
    turning_area                    TEXT,
    port_security                   TEXT,
    traffic_separation_scheme       TEXT,
    vessel_traffic_service          TEXT,
    navarea                         TEXT,                  -- NAVAREA number

    first_port_of_entry             TEXT,
    eta_message                     TEXT,                  -- Estimated Time of Arrival Message

    quarantine_pratique             TEXT,
    quarantine_sanitation           TEXT,
    quarantine_other                TEXT,

    pilotage_compulsory             TEXT,
    pilotage_available              TEXT,
    pilotage_local_assistance       TEXT,
    pilotage_advisable              TEXT,

    tugs_salvage                    TEXT,
    tugs_assistance                 TEXT,

    comm_telephone                  TEXT,
    comm_telefax                    TEXT,
    comm_radio                      TEXT,
    comm_radiotelephone             TEXT,
    comm_airport                    TEXT,
    comm_rail                       TEXT,
    search_and_rescue               TEXT,

    facility_wharves                TEXT,
    facility_anchorage              TEXT,
    facility_dangerous_cargo_anchor TEXT,
    facility_med_mooring            TEXT,
    facility_beach_mooring          TEXT,
    facility_ice_mooring            TEXT,
    facility_ro_ro                  TEXT,
    facility_solid_bulk             TEXT,
    facility_liquid_bulk            TEXT,
    facility_container              TEXT,
    facility_breakbulk              TEXT,
    facility_oil_terminal           TEXT,
    facility_lng_terminal           TEXT,
    facility_other                  TEXT,

    medical_facilities              TEXT,
    garbage_disposal                TEXT,
    chemical_holding_tank_disposal  TEXT,
    degaussing                      TEXT,
    dirty_ballast_disposal          TEXT,

    cranes_fixed                    TEXT,
    cranes_mobile                   TEXT,
    cranes_floating                 TEXT,
    cranes_container                TEXT,
    lifts_100plus_tons              TEXT,
    lifts_50_100_tons               TEXT,
    lifts_25_49_tons                TEXT,
    lifts_0_24_tons                 TEXT,

    services_longshoremen           TEXT,
    services_electricity            TEXT,
    services_steam                  TEXT,
    services_navigation_equipment   TEXT,
    services_electrical_repair      TEXT,
    services_ice_breaking           TEXT,
    services_diving                 TEXT,

    supplies_provisions             TEXT,
    supplies_potable_water          TEXT,
    supplies_fuel_oil               TEXT,
    supplies_diesel_oil             TEXT,
    supplies_aviation_fuel          TEXT,
    supplies_deck                   TEXT,
    supplies_engine                 TEXT,

    repairs                         TEXT,
    dry_dock                        TEXT,
    railway                         TEXT                   -- Slipway/Railway for hauling vessels

);

COMMENT ON TABLE ports IS
    'WPI (World Port Index / Pub 150) port definitions. One row = one port identified '
    'by UN/LOCODE. Provides physical characteristics and services metadata.';

-- Spatial index on geometry
CREATE INDEX IF NOT EXISTS idx_ports_geom
    ON ports USING GIST (geom);

-- Fast lookup by UN/LOCODE (used by analysis scripts)
CREATE INDEX IF NOT EXISTS idx_ports_un_locode
    ON ports (un_locode);

CREATE INDEX IF NOT EXISTS idx_ports_country
    ON ports (country_code);

-- Step 4: Add FK from port_terminals to ports (deferred so data can be loaded first)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_terminal_port') THEN
        ALTER TABLE port_terminals
            ADD CONSTRAINT fk_terminal_port
            FOREIGN KEY (port_id) REFERENCES ports(id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END;
$$;

-- Step 5: Relink `port_visits` to the new WPI `ports` table.
--         Since we are prioritizing WPI centers for extraction, 
--         port_visits.port_id must reference ports.id.
DO $$
BEGIN
    -- Drop old FK to port_terminals (renamed ports) if it exists
    ALTER TABLE port_visits DROP CONSTRAINT IF EXISTS port_visits_port_id_fkey;
    ALTER TABLE port_visits DROP CONSTRAINT IF EXISTS fk_port_visits_terminal;
    
    -- Add new FK pointing to top-level WPI ports (only if doesn't exist)
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_port_visits_wpi') THEN
        ALTER TABLE port_visits
            ADD CONSTRAINT fk_port_visits_wpi
            FOREIGN KEY (port_id) REFERENCES ports(id);
    END IF;
END;
$$;

COMMIT;
