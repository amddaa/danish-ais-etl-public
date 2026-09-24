"""
Route Visualization Script
=================================================
Writes Route Analysis JSON payloads consumed by the Astro site in web/.

Features:
- Routes colored by frequency / draught
- WPI Ports view: full Pub 150 metadata popups
- Terminals view: quay-level markers linked to parent WPI port
- Vessel details modal
"""

import json
import os

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

from source.config.db import get_db_connection

from source.config.logger import setup_logging
from source.analysis.web_data import WEB_DATA_DIR, dump_json
from source.schemas.tracker import RouteMapStats

logger = setup_logging(__name__)


def load_json_data(filename="route_analysis_results.json"):
    """Load the analysis results JSON file."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, filename)

    if not os.path.exists(json_path):
        logger.error(f"File not found: {json_path}")
        return None

    logger.info(f"Loading data from: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_wpi_ports_from_db():
    """Load all WPI ports from DB with full metadata and per-port terminal counts."""
    if not HAS_PSYCOPG2:
        logger.warning("psycopg2 not available – skipping WPI ports load.")
        return []
    try:
        conn = get_db_connection(connect_timeout=10)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                p.id,
                p.wpi_number,
                p.name,
                p.name_alternate,
                p.un_locode,
                p.country_code,
                p.region_name,
                p.world_water_body,
                p.harbor_size,
                p.harbor_type,
                p.harbor_use,
                p.shelter_afforded,
                p.max_vessel_draft_m,
                p.max_vessel_length_m,
                p.max_vessel_beam_m,
                p.channel_depth_m,
                p.cargo_pier_depth_m,
                p.oil_terminal_depth_m,
                p.lng_terminal_depth_m,
                p.tidal_range_m,
                p.vessel_traffic_service,
                p.traffic_separation_scheme,
                p.facility_ro_ro,
                p.facility_container,
                p.facility_liquid_bulk,
                p.facility_solid_bulk,
                p.facility_breakbulk,
                p.facility_oil_terminal,
                p.facility_lng_terminal,
                p.facility_other,
                p.repairs,
                p.dry_dock,
                p.railway,
                p.medical_facilities,
                p.garbage_disposal,
                p.chemical_holding_tank_disposal,
                p.dirty_ballast_disposal,
                p.cranes_fixed,
                p.cranes_mobile,
                p.cranes_floating,
                p.cranes_container,
                p.lifts_100plus_tons,
                p.lifts_50_100_tons,
                p.lifts_25_49_tons,
                p.lifts_0_24_tons,
                p.services_longshoremen,
                p.services_electricity,
                p.services_steam,
                p.services_navigation_equipment,
                p.services_electrical_repair,
                p.services_ice_breaking,
                p.services_diving,
                p.supplies_provisions,
                p.supplies_potable_water,
                p.supplies_fuel_oil,
                p.supplies_diesel_oil,
                p.supplies_deck,
                p.supplies_engine,
                ST_Y(p.geom::geometry) AS lat,
                ST_X(p.geom::geometry) AS lon,
                COUNT(t.id)            AS terminal_count
            FROM ports p
            LEFT JOIN port_terminals t ON t.port_id = p.id
            GROUP BY p.id
            ORDER BY p.name
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        logger.info(f"Loaded {len(rows)} WPI ports from DB.")
        return rows
    except Exception as e:
        logger.error(f"Failed to load WPI ports: {e}")
        return []


def load_terminals_from_db():
    """Load all port_terminals with their parent WPI port info."""
    if not HAS_PSYCOPG2:
        logger.warning("psycopg2 not available – skipping terminals load.")
        return []
    try:
        conn = get_db_connection(connect_timeout=10)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                t.id,
                t.name,
                ST_Y(t.geom::geometry) AS lat,
                ST_X(t.geom::geometry) AS lon,
                t.port_id              AS wpi_port_id,
                p.name                 AS wpi_port_name,
                p.un_locode            AS wpi_locode,
                p.harbor_size          AS wpi_harbor_size,
                p.max_vessel_draft_m   AS wpi_max_draught
            FROM port_terminals t
            LEFT JOIN ports p ON p.id = t.port_id
            ORDER BY t.name
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        logger.info(f"Loaded {len(rows)} terminals from DB.")
        return rows
    except Exception as e:
        logger.error(f"Failed to load terminals: {e}")
        return []


def load_port_geofences():
    """Load the generated port geofences for operational area visualization."""
    path = os.path.join(os.path.dirname(__file__), "..", "ports", "output", "port_geofences.json")
    if os.path.exists(path):
        logger.info(f"Loading geofences from: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"type": "FeatureCollection", "features": []}


def write_route_map_json(data, wpi_ports=None, terminals=None, geofences=None) -> None:
    """Write Route Analysis datasets as JSON for the Astro site."""
    if geofences is None:
        geofences = {"type": "FeatureCollection", "features": []}
    if wpi_ports is None:
        wpi_ports = []
    if terminals is None:
        terminals = []

    routes = data.get("routes", [])
    ports = data.get("ports", [])
    vessels_list = data.get("vessels", [])
    metadata = data.get("metadata", {})

    vessels_by_mmsi = {str(v["mmsi"]): v for v in vessels_list}
    stats = RouteMapStats(
        routes=int(metadata.get("total_routes", len(routes))),
        ports=int(metadata.get("total_ports", len(ports))),
        vessels=int(metadata.get("total_vessels", len(vessels_list))),
        trips=int(metadata.get("total_trips", 0)),
    )

    out_dir = WEB_DATA_DIR / "routes_map"
    dump_json(out_dir / "routes.json", routes)
    dump_json(out_dir / "ports.json", ports)
    dump_json(out_dir / "vessels.json", vessels_by_mmsi)
    dump_json(out_dir / "wpi_ports.json", wpi_ports)
    dump_json(out_dir / "terminals.json", terminals)
    dump_json(out_dir / "geofences.json", geofences)
    dump_json(out_dir / "stats.json", stats.model_dump(mode="json"))
    logger.info("Wrote Route Analysis JSON under %s", out_dir)


def main():
    logger.info("Starting route visualization...")

    data = load_json_data()
    if not data:
        return

    wpi_ports = load_wpi_ports_from_db()
    terminals = load_terminals_from_db()
    geofences = load_port_geofences()

    metadata = data.get("metadata", {})
    logger.info(
        f"Loaded: {metadata.get('total_routes', 0)} routes, "
        f"{metadata.get('total_ports', 0)} route-ports, "
        f"{len(wpi_ports)} WPI ports, {len(terminals)} terminals"
    )

    write_route_map_json(data, wpi_ports=wpi_ports, terminals=terminals, geofences=geofences)
    logger.info("Done!")


if __name__ == "__main__":
    main()
