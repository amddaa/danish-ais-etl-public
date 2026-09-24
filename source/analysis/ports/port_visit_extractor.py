import psycopg2
import json
from datetime import datetime, timezone
import os

from source.config.logger import setup_logging
logger = setup_logging(__name__)
import logging
logger.setLevel(logging.INFO)

from source.schemas import PortVisitRecord, VoyageRecord, ExtractionMetadata
from source.config.db import get_db_connection, connection_kwargs
from shapely.geometry import Point
import shapely.vectorized
from source.analysis.utils.trajectory_utils import clean_trajectory, apply_median_filter

# Tthresholds (knots / hours / metres)
SOG_THRESHOLD_LOW = 1.0           # Knots to trigger STOPPED_IN_PORT
SOG_THRESHOLD_HIGH = 3.0          # Knots to unequivocally terminate a visit
MIN_STAY_HOURS = 1.0              # Minimum stay duration to consider it a valid port call
GAP_HOURS = 12.0                  # Time after which a gap is scrutinized
MAX_GAP_HOURS = 48.0              # Absolute max gap before unconditional split (moored ships powering down)

# Expanded radii to cover outer cargo/tanker terminals (e.g. Naftoport ~4–5 km from city centre)
PORT_RADIUS_M = 5000.0            # Max distance to port center to trigger a visit (meters)
PORT_BUFFER_M = 7500.0            # Relaxed buffer so jitter does not prematurely close a visit
EARTH_RADIUS_M = 6_371_000.0
MAX_SPEED_KNOTS = 50.0

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

MAX_WORKERS = max(1, (os.cpu_count() or 1) - 1)
IO_EXECUTOR_WORKERS = 2
BATCH_SIZE = 1000                  # Number of records before flushing to DB
CHUNK_SIZE = 200                   # Number of vessels to fetch in one DB query

def effective_state(sog, nav_status, in_port_radius):
    """SOG has priority; nav_status is only a hint when sog is low."""
    if sog > SOG_THRESHOLD_HIGH:
        return "UNDERWAY"  # Regardless of nav_status
    if in_port_radius and sog < SOG_THRESHOLD_LOW:
        return "STOPPED_IN_PORT"
    if nav_status in ('Moored', 'At anchor', '1', '5') and sog < SOG_THRESHOLD_LOW:
        return "STOPPED_IN_PORT" 
    return "TRANSITING"

def load_vessel_metadata(cur):
    """Preloads vessel statics (ship_type, cargo_type, dimensions)."""
    cur.execute("SELECT mmsi, ship_type, cargo_type, length_m, width_m, last_known_draught_m FROM vessels")
    metadata = {}
    for r in cur.fetchall():
        metadata[r[0]] = {
            'ship_type': r[1],
            'cargo_type': r[2],
            'length_m': r[3],
            'width_m': r[4],
            'last_known_draught_m': r[5]
        }
    return metadata

def get_last_destination(points, current_index):
    """Searches backward from current_index to find the last declared destination."""
    for i in range(current_index, -1, -1):
        if points[i]['destination'] and points[i]['destination'].strip():
            return points[i]['destination'].strip()
    return None

def finalize_visit(visit, last_point, visits_list, min_stay_hours):
    """Validates and appends a closed visit to the master list."""
    duration = (last_point['timestamp'] - visit['arrival_time']).total_seconds() / 3600.0
    
    if duration >= min_stay_hours:
        draughts = [p['draught'] for p in visit['points'] if p['draught'] is not None and p['draught'] > 0]
        med_draught = sorted(draughts)[len(draughts)//2] if draughts else None
        
        visits_list.append({
            'port_id': visit['port_id'],
            'arrival_time': visit['arrival_time'],
            'departure_time': last_point['timestamp'],
            'stay_duration_hours': duration,
            'draught_m': med_draught,
            'declared_destination': visit['declared_destination'],
            'n_positions': len(visit['points'])
        })
        return True
    return False

import numpy as np
from scipy.spatial import cKDTree  # pyrefly: ignore[missing-module-attribute]
from typing import Any

# Lon/lat → ECEF-style cartesian on a sphere (for cKDTree Euclidean queries)
def get_cartesian(lon, lat):
    R = EARTH_RADIUS_M 
    lon_rad = np.radians(lon)
    lat_rad = np.radians(lat)
    x = R * np.cos(lat_rad) * np.cos(lon_rad)
    y = R * np.cos(lat_rad) * np.sin(lon_rad)
    z = R * np.sin(lat_rad)
    return x, y, z

def haversine_dist(lon1, lat1, lon2, lat2):
    """Returns the great-circle distance in meters between two spherical points."""
    R = EARTH_RADIUS_M
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(a))
    return R * c

def load_ports_tree(cur):
    """Load ports and build a cKDTree over cartesian coordinates."""
    cur.execute("SELECT id, ST_X(geom::geometry), ST_Y(geom::geometry), name FROM ports")
    rows = cur.fetchall()
    
    ports_dict = {}
    coords = []
    ids = []
    
    for idx, r in enumerate(rows):
        pid, lon, lat, name = r
        ports_dict[pid] = {'lon': lon, 'lat': lat, 'name': name}
        x, y, z = get_cartesian(lon, lat)
        coords.append([x, y, z])
        ids.append(pid)
        
    tree = cKDTree(coords)
    return ports_dict, tree, ids

def extract_visits_from_rows(mmsi, rows, ports_dict, tree, port_ids_map, geofence_polygons):
    if not rows:
        return []
        
    logger.debug(f"Processing {len(rows)} points for MMSI {mmsi}")
    
    # Row layout [lat, lon, timestamp, sog, ...] for trajectory utils
    formatted_points = [[r[2], r[1], r[0], r[3], r[4], r[5], r[6]] for r in rows]
    
    cleaned = clean_trajectory(formatted_points, max_speed_knots=MAX_SPEED_KNOTS)
    
    if len(cleaned) >= 5:
        cleaned = apply_median_filter(cleaned, window_size=5)
        
    if not cleaned:
        return []
        
    # Remap to (timestamp, lon, lat, sog, ...) for the vectorized loop below
    rows = [[p[2], p[1], p[0], p[3], p[4], p[5], p[6]] for p in cleaned]
    
    rows_arr = np.array(rows, dtype=object)
    lons = rows_arr[:, 1].astype(float)
    lats = rows_arr[:, 2].astype(float)
    
    R = EARTH_RADIUS_M
    lon_rad = np.radians(lons)
    lat_rad = np.radians(lats)
    x = R * np.cos(lat_rad) * np.cos(lon_rad)
    y = R * np.cos(lat_rad) * np.sin(lon_rad)
    z = R * np.sin(lat_rad)
    points_cart = np.column_stack((x, y, z))
    
    distances, closest_idx = tree.query(points_cart)
    
    # Radius first; refine with polygon contains when a geofence exists
    in_port_radius_arr = distances <= PORT_RADIUS_M
    
    if geofence_polygons:
        unique_port_indices = np.unique(closest_idx)
        for p_idx in unique_port_indices:
            pid = port_ids_map[p_idx]
            if pid in geofence_polygons:
                mask = (closest_idx == p_idx) & (distances <= PORT_RADIUS_M)
                if np.any(mask):
                    poly = geofence_polygons[pid]
                    in_port_radius_arr[mask] = shapely.vectorized.contains(poly, lons[mask], lats[mask])

    points: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        points.append({
            'timestamp': r[0], 'lon': r[1], 'lat': r[2],
            'sog': r[3] if r[3] is not None else 0.0,
            'nav_status': r[4], 'destination': r[5], 'draught': r[6],
            'port_id': port_ids_map[closest_idx[i]],
            'dist_m': distances[i],
            'in_port_radius': in_port_radius_arr[i]
        })

    visits: list[dict[str, Any]] = []
    current_visit: dict[str, Any] | None = None
    last_p = points[0]
    
    cons_underway = 0
    cons_away = 0
    
    for i, p in enumerate(points):
        in_port_radius = p['in_port_radius']
        state_result = effective_state(p['sog'], p['nav_status'], in_port_radius)
    
        if current_visit:
            time_gap = (p['timestamp'] - last_p['timestamp']).total_seconds() / 3600.0
            
            curr_port_info = ports_dict[current_visit['port_id']]
            dist_to_current_port = haversine_dist(p['lon'], p['lat'], curr_port_info['lon'], curr_port_info['lat'])
            
            # Within buffer: keep current port even if a neighbour is geometrically closer
            if dist_to_current_port <= PORT_BUFFER_M:
                p['port_id'] = current_visit['port_id']

            if state_result == "UNDERWAY":
                cons_underway += 1
            elif state_result == "STOPPED_IN_PORT":
                cons_underway = 0
            else:
                cons_underway = max(0, cons_underway - 1)
                
            if dist_to_current_port > PORT_BUFFER_M:
                cons_away += 1
            else:
                cons_away = 0
                
            must_close = False
            if time_gap > MAX_GAP_HOURS:
                must_close = True  
            elif time_gap > GAP_HOURS and (p['port_id'] != current_visit['port_id'] or dist_to_current_port > PORT_BUFFER_M):
                must_close = True  
            elif cons_underway >= 3 and not in_port_radius:
                must_close = True  
            elif cons_away >= 3:
                must_close = True  
            elif p['port_id'] != current_visit['port_id'] and not in_port_radius and (cons_underway >= 2 or cons_away >= 2):
                must_close = True  
                
            if must_close:
                close_point = current_visit['points'][-1] if current_visit['points'] else last_p
                finalize_visit(current_visit, close_point, visits, MIN_STAY_HOURS)
                current_visit = None
                cons_underway = 0
                cons_away = 0
            else:
                current_visit['points'].append(p)
                
        if not current_visit:
            if state_result == "STOPPED_IN_PORT" and in_port_radius:
                dest = get_last_destination(points, i)
                current_visit = {
                    'port_id': p['port_id'],
                    'arrival_time': p['timestamp'],
                    'points': [p],
                    'declared_destination': dest,
                }
                logger.debug(f"MMSI {mmsi}: Visit OPENED at port {p['port_id']} ({ports_dict[p['port_id']]['name']})")
                cons_underway = 0
                cons_away = 0
                    
        last_p = p
        
    if current_visit:
        finalize_visit(current_visit, last_p, visits, MIN_STAY_HOURS)

    return visits

def extract_voyages_from_visits(mmsi, visits, vessel_meta):
    """Build voyage dicts for consecutive port-visit pairs."""
    voyages = []
    for i in range(len(visits) - 1):
        origin = visits[i]
        dest   = visits[i + 1]
        
        if origin['departure_time'] >= dest['arrival_time']:
            continue # Anomaly in data or overlapping visits
            
        voyages.append({
            "mmsi":                  mmsi,
            "ship_type":             vessel_meta.get("ship_type"),
            "cargo_type":            vessel_meta.get("cargo_type"),
            "origin_port_id":        origin["port_id"],
            "destination_port_id":   dest["port_id"],
            "departure_time":        origin["departure_time"],
            "arrival_time":          dest["arrival_time"],
            "voyage_duration_hours": (dest["arrival_time"] - origin["departure_time"]).total_seconds() / 3600,
            "draught_at_origin_m":   origin["draught_m"],
            "draught_at_dest_m":     dest["draught_m"],
            "declared_destination":  origin["declared_destination"],
        })
    return voyages

from psycopg2 import pool
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed

db_pool: pool.ThreadedConnectionPool | None = None
_worker_static_data: dict[str, Any] = {}

def init_worker(ports_dict, tree, port_ids_map, geofence_polygons):
    global _worker_static_data
    _worker_static_data['ports_dict'] = ports_dict
    _worker_static_data['tree'] = tree
    _worker_static_data['port_ids_map'] = port_ids_map
    _worker_static_data['geofence_polygons'] = geofence_polygons

def fetch_mmsi_data(mmsi_batch):
    assert db_pool is not None
    conn = db_pool.getconn()
    cur = conn.cursor()
    mmsi_to_rows = defaultdict(list)
    
    try:
        cur.execute("SELECT mmsi, MAX(departure_time) FROM port_visits WHERE mmsi IN %s GROUP BY mmsi", (tuple(mmsi_batch),))
        last_times = {r[0]: r[1] for r in cur.fetchall()}
        
        earliest_time = min(last_times.values()) if last_times and len(last_times) == len(mmsi_batch) else None
        time_filter = f"AND timestamp > '{earliest_time}'" if earliest_time else ""

        query = f"""
        SELECT 
            mmsi,
            last(timestamp, timestamp) as actual_timestamp, 
            ST_X(last(position_geog, timestamp)::geometry) as longitude, 
            ST_Y(last(position_geog, timestamp)::geometry) as latitude,
            last(speed_over_ground, timestamp) as sog,
            last(navigational_status, timestamp) as nav_status, 
            last(destination, timestamp) as destination, 
            last(draught_m, timestamp) as draught
        FROM ais_positions
        WHERE mmsi IN %s {time_filter}
        GROUP BY mmsi, time_bucket('10 minutes', timestamp)
        ORDER BY mmsi, actual_timestamp ASC;
        """
        
        cur.execute(query, (tuple(mmsi_batch),))
        rows = cur.fetchall()
        
        for r in rows:
            row_mmsi = r[0]
            row_data = r[1:]
            m_last = last_times.get(row_mmsi)
            if m_last and row_data[0] <= m_last:
                continue
            mmsi_to_rows[row_mmsi].append(row_data)
            
    except Exception as e:
        logger.error(f"DB Error in fetch_mmsi_data: {e}")
    finally:
        cur.close()
        db_pool.putconn(conn)
        
    return mmsi_to_rows

def process_vessel_logic(mmsi, rows):
    global _worker_static_data
    try:
        visits = extract_visits_from_rows(
            mmsi, rows, 
            _worker_static_data['ports_dict'], 
            _worker_static_data['tree'], 
            _worker_static_data['port_ids_map'], 
            _worker_static_data['geofence_polygons']
        )
        return mmsi, visits
    except Exception as e:
        logger.error(f"Logic Error for MMSI {mmsi}: {e}")
        return mmsi, []

def process_mmsi_batch(mmsi_batch, ports_dict, tree, port_ids_map, geofence_polygons):
    mmsi_to_rows = fetch_mmsi_data(mmsi_batch)
    all_visits = []
    for mmsi in mmsi_batch:
        rows = mmsi_to_rows.get(mmsi, [])
        _, visits = process_vessel_logic(mmsi, rows)
        all_visits.append((mmsi, visits))
    return all_visits

def run_extraction():
    global db_pool
    logger.info("Initializing State Machine Extractor directly into Multi-threaded mode...")
    
    db_pool = pool.ThreadedConnectionPool(1, 12, **connection_kwargs(connect_timeout=10))
    
    main_conn = get_db_connection(connect_timeout=10)
    main_cur = main_conn.cursor()
    
    try:
        main_cur.execute("SELECT 1 FROM port_visits LIMIT 1")
    except psycopg2.Error:
        logger.error("Table 'port_visits' does not exist. Apply migrations first!")
        main_conn.close()
        db_pool.closeall()
        return

    logger.info("Preloading vessel static attributes, spatial trees, and geofences...")
    vessels_md = load_vessel_metadata(main_cur)
    ports_dict, tree, port_ids_map = load_ports_tree(main_cur)
    
    GEOFENCES_PATH = os.path.join(OUTPUT_DIR, "port_geofences.json")
    geofence_polygons = {}
    if os.path.exists(GEOFENCES_PATH):
        from shapely.geometry import shape
        with open(GEOFENCES_PATH, "r", encoding="utf-8") as f:
            gf_data = json.load(f)
            for feat in gf_data['features']:
                pid = feat['properties']['port_id']
                geofence_polygons[pid] = shape(feat['geometry'])
        logger.info(f"Loaded {len(geofence_polygons)} geofences for precise spatial filtering.")
    else:
        logger.warning("port_geofences.json not found! Falling back to static radius logic.")

    logger.info("Fetching target MMSIs ...")
    # main_cur.execute("SELECT mmsi FROM vessels WHERE ship_type IN ('Tanker', 'Cargo')")
    main_cur.execute("SELECT mmsi FROM vessels")
    all_mmsis = [r[0] for r in main_cur.fetchall()]
    
    logger.info(f"Identified {len(all_mmsis)} unique vessels for extraction.")

    total_inserted = 0
    batch_records = []
    
    from psycopg2.extras import execute_values
    
    insert_query = """
        INSERT INTO port_visits (
            mmsi, port_id, arrival_time, departure_time, 
            draught_m, ship_type, cargo_type, length_m, width_m,
            declared_destination, n_positions
        ) VALUES %s
        ON CONFLICT (mmsi, port_id, arrival_time) DO NOTHING
    """
    
    def flush_batch(conn, cur, records):
        """execute_values INSERT with ON CONFLICT DO NOTHING."""
        if not records:
            return
        try:
            execute_values(cur, insert_query, records, page_size=len(records))
            conn.commit()
        except Exception as e:
            logger.error(f"DB Flush Error: {e}")
            conn.rollback()
        
    logger.info(f"Firing up ThreadPool (IO) and ProcessPool (CPU) with {MAX_WORKERS} workers...")
    
    OUTPUT_VISITS = os.path.join(OUTPUT_DIR, "port_visits.jsonl")
    OUTPUT_VOYAGES = os.path.join(OUTPUT_DIR, "voyages.jsonl")
    OUTPUT_METADATA = os.path.join(OUTPUT_DIR, "extraction_metadata.json")
    
    for f_path in [OUTPUT_VISITS, OUTPUT_VOYAGES, OUTPUT_METADATA]:
        if os.path.exists(f_path):
            os.remove(f_path)
            logger.debug(f"Cleared previous output: {os.path.basename(f_path)}")
    
    total_voyages = 0
    total_visits = 0
    
    try:
        with open(OUTPUT_VISITS, "w", encoding="utf-8") as f_visits, \
             open(OUTPUT_VOYAGES, "w", encoding="utf-8") as f_voyages:
            
            mmsi_chunks = [all_mmsis[i:i + CHUNK_SIZE] for i in range(0, len(all_mmsis), CHUNK_SIZE)]
            
            processed_count = 0
            all_cpu_futures = set()
            active_io = {}
            chunk_idx = 0
            
            with ThreadPoolExecutor(max_workers=IO_EXECUTOR_WORKERS) as io_executor, \
                 ProcessPoolExecutor(
                     max_workers=MAX_WORKERS,
                     initializer=init_worker,
                     initargs=(ports_dict, tree, port_ids_map, geofence_polygons)
                 ) as cpu_executor:
                
                logger.info(f"Starting throttled pipeline for {len(mmsi_chunks)} chunks...")
                
                while chunk_idx < len(mmsi_chunks) or active_io or all_cpu_futures:
                    while len(active_io) < 2 and chunk_idx < len(mmsi_chunks):
                        chunk = mmsi_chunks[chunk_idx]
                        f_io = io_executor.submit(fetch_mmsi_data, chunk)
                        active_io[f_io] = chunk
                        chunk_idx += 1
                        logger.info(f"DB Fetch: Requested chunk {chunk_idx}/{len(mmsi_chunks)}")

                    done_io = [f for f in active_io if f.done()]
                    for f in done_io:
                        try:
                            mmsi_to_rows = f.result()
                            logger.info(f"DB Fetch: Received {len(mmsi_to_rows)} vessels. Submitting to CPU...")
                            for mmsi, rows in mmsi_to_rows.items():
                                all_cpu_futures.add(cpu_executor.submit(process_vessel_logic, mmsi, rows))
                        except Exception as e:
                            logger.error(f"IO Error in chunk: {e}")
                        finally:
                            del active_io[f]

                    done_cpu = [f for f in all_cpu_futures if f.done()]
                    for f in done_cpu:
                        try:
                            mmsi, visits = f.result()
                            processed_count += 1
                            if visits:
                                v_meta = vessels_md.get(mmsi, {})
                                now_str = datetime.now(timezone.utc)
                                for v in visits:
                                    visit_draught = v.get('draught_m')
                                    v['draught_m'] = visit_draught
                                    batch_records.append((
                                        mmsi, v['port_id'], v['arrival_time'], v['departure_time'],
                                        visit_draught, v_meta.get('ship_type'), v_meta.get('cargo_type'), 
                                        v_meta.get('length_m'), v_meta.get('width_m'),
                                        v['declared_destination'], v['n_positions']
                                    ))
                                    try:
                                        total_visits += 1
                                        v_json = v.copy()
                                        v_json.update({'mmsi':mmsi, 'id':total_visits, 'created_at':now_str, **v_meta})
                                        f_visits.write(PortVisitRecord.model_validate(v_json).model_dump_json() + "\n")
                                    except Exception: pass

                                voyages = extract_voyages_from_visits(mmsi, visits, v_meta)
                                for voy in voyages:
                                    try:
                                        f_voyages.write(VoyageRecord.model_validate(voy).model_dump_json() + "\n")
                                        total_voyages += 1
                                    except Exception: pass
                            
                            if len(batch_records) >= BATCH_SIZE:
                                flush_batch(main_conn, main_cur, batch_records)
                                total_inserted += len(batch_records)
                                batch_records.clear()
                                f_visits.flush()
                                f_voyages.flush()
                                logger.info(f"DB Flush (COPY): Total {total_inserted}")

                            if processed_count % 25 == 0 or processed_count == len(all_mmsis):
                                progress = (processed_count / len(all_mmsis)) * 100
                                logger.info(f"Progress: {progress:.1f}% ({processed_count}/{len(all_mmsis)}) | Visits: {total_visits}")
                        except Exception as e:
                            logger.error(f"CPU Worker Error: {e}")
                        finally:
                            all_cpu_futures.remove(f)
                    
                    import time
                    time.sleep(0.1)

            if batch_records:
                flush_batch(main_conn, main_cur, batch_records)
                total_inserted += len(batch_records)
                logger.info(f"Final DB Flush: Total {total_inserted}")

        meta = ExtractionMetadata(
            generated_at=datetime.now(timezone.utc),
            total_visits=total_visits,
            total_voyages=total_voyages,
            n_vessels_processed=len(all_mmsis)
        )
        with open(OUTPUT_METADATA, "w", encoding="utf-8") as f:
            f.write(meta.model_dump_json(indent=2))

    except Exception as e:
        logger.error(f"Fatal error during extraction: {e}")
        raise
    finally:
        main_cur.close()
        main_conn.close()
        db_pool.closeall()

if __name__ == "__main__":
    run_extraction()
