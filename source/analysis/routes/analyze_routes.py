"""Route analysis: collect vessel trips, aggregate routes/ports/vessels to JSON."""

import psycopg2
import json
import os
import collections
import logging
import decimal
from datetime import datetime, timezone
from typing import Any

from source.config.logger import setup_logging
logger = setup_logging(__name__)

from source.config.db import get_db_connection

# Parameters
STOP_DURATION_MINS = 30
PORT_MATCH_RADIUS_M = 1000
MIN_TRIP_DISTANCE_M = 100_000  # 100 km minimum to count as a trip
DEFAULT_VESSEL_LIMIT = 5000
PARTIAL_RESULTS_FILE = "route_analysis_partial.jsonl"
FINAL_RESULTS_FILE = "route_analysis_results.json"


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder for Decimal types from PostgreSQL."""
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        return super().default(o)


def verify_ports_table(cur):
    try:
        cur.execute("SELECT COUNT(*) FROM ports")
        count = cur.fetchone()[0]
        if count == 0:
            logger.warning("'ports' table is empty. Run 'import_ports.py' first.")
            return False
        return True
    except psycopg2.Error:
        logger.warning("'ports' table missing. Run 'import_ports.py' first.")
        return False


def get_target_mmsis(cur, limit):
    logger.info(f"Selecting top {limit} Cargo/Tanker vessels...")
    sql = """
        SELECT mmsi 
        FROM vessels 
        WHERE ship_type IN ('Cargo', 'Tanker')
          AND (last_seen_at - first_seen_at) > interval '3 days'
        ORDER BY (last_seen_at - first_seen_at) DESC
        LIMIT %s
    """
    cur.execute(sql, (limit,))
    return [row[0] for row in cur.fetchall()]


def load_processed_mmsis():
    processed = set()
    if os.path.exists(PARTIAL_RESULTS_FILE):
        with open(PARTIAL_RESULTS_FILE, "r") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    processed.add(data["mmsi"])
                except json.JSONDecodeError:
                    continue
    return processed


def save_partial_result(mmsi, trips):
    with open(PARTIAL_RESULTS_FILE, "a") as f:
        record = {"mmsi": mmsi, "trips": trips}
        f.write(json.dumps(record, cls=DecimalEncoder) + "\n")


def analyze_vessel(cur, mmsi):
    """Port-to-port trips for one vessel with origin/dest draught stats and distance."""
    sql = f"""
    WITH raw_stops AS (
        SELECT 
            timestamp, 
            position_geog,
            draught_m,
            CASE 
                WHEN timestamp - LAG(timestamp) OVER (ORDER BY timestamp) > INTERVAL '30 minutes' 
                THEN 1 ELSE 0 
            END as is_new_group
        FROM ais_positions
        WHERE mmsi = %s
          AND (speed_over_ground < 1.0 OR navigational_status IN ('1', '5', 'Anchored', 'Moored'))
          AND (EXTRACT(MINUTE FROM timestamp)::INTEGER %% 10 = 0)
    ),
    grouped_stops AS (
        SELECT 
            *,
            SUM(is_new_group) OVER (ORDER BY timestamp) as grp_id
        FROM raw_stops
    ),
    valid_stops AS (
        SELECT
            grp_id,
            MIN(timestamp) as start_time,
            MAX(timestamp) as end_time,
            ST_SetSRID(ST_MakePoint(
                AVG(ST_X(position_geog::geometry)), 
                AVG(ST_Y(position_geog::geometry))
            ), 4326) as geom,
            MIN(NULLIF(draught_m, 0)) as min_draught,
            AVG(NULLIF(draught_m, 0)) as avg_draught,
            MAX(draught_m) as max_draught
        FROM grouped_stops
        GROUP BY grp_id
        HAVING MAX(timestamp) - MIN(timestamp) >= INTERVAL '{STOP_DURATION_MINS} minutes'
    ),
    port_stops AS (
        SELECT 
            s.start_time,
            s.end_time,
            s.geom,
            p.id as port_id,
            p.name as port_name,
            ST_X(p.geom::geometry) as port_lon,
            ST_Y(p.geom::geometry) as port_lat,
            s.min_draught,
            s.avg_draught,
            s.max_draught
        FROM valid_stops s
        JOIN ports p ON ST_DWithin(s.geom::geography, p.geom, {PORT_MATCH_RADIUS_M})
    ),
    ordered_trips AS (
        SELECT 
            port_id,
            port_name,
            port_lon,
            port_lat,
            min_draught as o_min,
            avg_draught as o_avg,
            max_draught as o_max,
            start_time,
            LEAD(port_id) OVER (ORDER BY start_time) as next_port_id,
            LEAD(port_name) OVER (ORDER BY start_time) as next_port,
            LEAD(port_lon) OVER (ORDER BY start_time) as next_port_lon,
            LEAD(port_lat) OVER (ORDER BY start_time) as next_port_lat,
            LEAD(min_draught) OVER (ORDER BY start_time) as d_min,
            LEAD(avg_draught) OVER (ORDER BY start_time) as d_avg,
            LEAD(max_draught) OVER (ORDER BY start_time) as d_max,
            LEAD(geom) OVER (ORDER BY start_time) as next_geom,
            geom as curr_geom
        FROM port_stops
    )
    SELECT 
        port_id as origin_id,
        port_name as origin,
        port_lon as origin_lon,
        port_lat as origin_lat,
        o_min, o_avg, o_max,
        next_port_id as dest_id,
        next_port as destination,
        next_port_lon as dest_lon,
        next_port_lat as dest_lat,
        d_min, d_avg, d_max,
        ST_Distance(curr_geom::geography, next_geom::geography) as dist
    FROM ordered_trips
    WHERE next_port IS NOT NULL 
      AND port_id != next_port_id
      AND ST_Distance(curr_geom::geography, next_geom::geography) > {MIN_TRIP_DISTANCE_M};
    """
    cur.execute(sql, (mmsi,))
    return cur.fetchall()


def get_stats(data_list):
    if not data_list:
        return None
    filtered = [x for x in data_list if x is not None]
    if not filtered:
        return None
    return {
        "min": round(min(filtered), 2),
        "avg": round(sum(filtered) / len(filtered), 2),
        "max": round(max(filtered), 2)
    }


def analyze_routes_sql(limit=DEFAULT_VESSEL_LIMIT):
    conn = get_db_connection(connect_timeout=10)
    cur = conn.cursor()

    if not verify_ports_table(cur):
        return

    try:
        processed_mmsis = load_processed_mmsis()
        logger.info(f"Resuming... {len(processed_mmsis)} vessels already processed.")

        all_mmsis = get_target_mmsis(cur, limit)
        mmsis_to_process = [m for m in all_mmsis if m not in processed_mmsis]
        
        logger.info(f"Found {len(all_mmsis)} targets. {len(mmsis_to_process)} remaining.")
        
        for i, mmsi in enumerate(mmsis_to_process):
            try:
                trips = analyze_vessel(cur, mmsi)
                save_partial_result(mmsi, trips)
                
                if (i + 1) % 10 == 0:
                    logger.info(f"Processed {i + 1}/{len(mmsis_to_process)} ({len(trips)} trips for MMSI {mmsi})")
                     
            except Exception as e:
                logger.error(f"Error processing MMSI {mmsi}: {e}")
                conn.rollback()
                continue

        logger.info("Data collection complete.")

        logger.info("Aggregating results...")
        
        route_trips = collections.defaultdict(list)  # (oid, did) -> list of trip data
        port_draughts = collections.defaultdict(list)  # port_id -> list of draughts
        port_info = {}  # port_id -> {name, lat, lon}
        vessel_global_stats = collections.defaultdict(list)  # mmsi -> list of draughts
        
        with open(PARTIAL_RESULTS_FILE, "r") as f:
            for line in f:
                try:
                    record = json.loads(line)
                    mmsi = record['mmsi']
                    trips = record['trips']
                    
                    if not trips:
                        continue
                    
                    if len(trips[0]) != 15:
                        continue
                        
                    for trip in trips:
                        (origin_id, origin_name, o_lon, o_lat, o_min, o_avg, o_max,
                         dest_id, dest_name, d_lon, d_lat, d_min, d_avg, d_max, dist) = trip
                        
                        route_key = (origin_id, dest_id)
                        
                        trip_draught = max(o_max or 0, d_max or 0)
                        route_trips[route_key].append({
                            "mmsi": mmsi,
                            "draught": trip_draught,
                            "origin_draught": o_max,
                            "dest_draught": d_max,
                            "distance": dist
                        })
                        
                        if origin_id not in port_info:
                            port_info[origin_id] = {"name": origin_name, "lat": o_lat, "lon": o_lon}
                        if dest_id not in port_info:
                            port_info[dest_id] = {"name": dest_name, "lat": d_lat, "lon": d_lon}
                        
                        if o_max:
                            port_draughts[origin_id].append(o_max)
                        if d_max:
                            port_draughts[dest_id].append(d_max)
                        
                        if trip_draught > 0:
                            vessel_global_stats[mmsi].append(trip_draught)

                except Exception:
                    continue

        logger.info("Fetching vessel details from database...")
        vessel_details = {}  # mmsi -> {id, name, ship_type}
        all_mmsis = list(vessel_global_stats.keys())
        
        for i in range(0, len(all_mmsis), 1000):
            batch = all_mmsis[i:i+1000]
            cur.execute("""
                SELECT id, mmsi, name, ship_type 
                FROM vessels 
                WHERE mmsi = ANY(%s)
            """, (batch,))
            for row in cur.fetchall():
                vessel_details[row[1]] = {
                    "vessel_id": row[0],
                    "name": row[2],
                    "ship_type": row[3]
                }

        logger.info("Building final output...")
        
        final_routes: list[dict[str, Any]] = []
        for (origin_id, dest_id), trip_list in route_trips.items():
            if origin_id not in port_info or dest_id not in port_info:
                continue
                
            o_info = port_info[origin_id]
            d_info = port_info[dest_id]
            
            all_draughts = [t["draught"] for t in trip_list if t["draught"]]
            
            vessel_agg = collections.defaultdict(list)
            for t in trip_list:
                if t["draught"]:
                    vessel_agg[t["mmsi"]].append(t["draught"])
            
            vessels_on_route: list[dict[str, Any]] = []
            for mmsi, draughts in vessel_agg.items():
                v_info = vessel_details.get(mmsi, {})
                vessels_on_route.append({
                    "mmsi": mmsi,
                    "vessel_id": v_info.get("vessel_id"),
                    "name": v_info.get("name", "Unknown"),
                    "ship_type": v_info.get("ship_type"),
                    "trip_count": len(draughts),
                    "draught_stats": get_stats(draughts)
                })
            
            vessels_on_route.sort(key=lambda x: int(x["trip_count"]), reverse=True)
            
            final_routes.append({
                "route_id": f"{origin_id}_{dest_id}",
                "origin": {
                    "port_id": origin_id,
                    "name": o_info["name"],
                    "geometry": {
                        "type": "Point",
                        "coordinates": [o_info["lon"], o_info["lat"]]
                    }
                },
                "destination": {
                    "port_id": dest_id,
                    "name": d_info["name"],
                    "geometry": {
                        "type": "Point",
                        "coordinates": [d_info["lon"], d_info["lat"]]
                    }
                },
                "total_trips": len(trip_list),
                "draught_stats": get_stats(all_draughts),
                "vessels": vessels_on_route
            })
        
        final_routes.sort(key=lambda x: int(x["total_trips"]), reverse=True)
        
        final_ports: list[dict[str, Any]] = []
        for port_id, draughts in port_draughts.items():
            if port_id not in port_info:
                continue
            info = port_info[port_id]
            port_entry: dict[str, Any] = {
                "port_id": port_id,
                "name": info["name"],
                "geometry": {
                    "type": "Point",
                    "coordinates": [info["lon"], info["lat"]]
                },
                "total_visits": len(draughts)
            }
            stats = get_stats(draughts)
            if stats:
                port_entry["draught_stats"] = stats
            final_ports.append(port_entry)
        
        final_ports.sort(key=lambda x: int(x["total_visits"]), reverse=True)
        
        final_vessels: list[dict[str, Any]] = []
        for mmsi, draughts in vessel_global_stats.items():
            v_info = vessel_details.get(mmsi, {})
            final_vessels.append({
                "mmsi": mmsi,
                "vessel_id": v_info.get("vessel_id"),
                "name": v_info.get("name", "Unknown"),
                "ship_type": v_info.get("ship_type"),
                "total_trips": len(draughts),
                "draught_stats": get_stats(draughts)
            })
        
        final_vessels.sort(key=lambda x: int(x["total_trips"]), reverse=True)
        
        final_output = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_routes": len(final_routes),
                "total_ports": len(final_ports),
                "total_vessels": len(final_vessels),
                "total_trips": sum(int(r["total_trips"]) for r in final_routes)
            },
            "routes": final_routes,
            "ports": final_ports,
            "vessels": final_vessels
        }

        with open(FINAL_RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=2, ensure_ascii=False, cls=DecimalEncoder)
        
        logger.info(f"Results saved to {FINAL_RESULTS_FILE}")
        logger.info(f"  Routes: {len(final_routes)}, Ports: {len(final_ports)}, Vessels: {len(final_vessels)}")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    analyze_routes_sql(limit=DEFAULT_VESSEL_LIMIT)
