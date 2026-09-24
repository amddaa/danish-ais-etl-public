import json
import os
import time
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from psycopg2 import pool
from source.config.db import connection_kwargs
from source.config.logger import setup_logging
from source.analysis.utils.trajectory_utils import clean_trajectory, apply_median_filter, simplify_trajectory
from source.analysis.web_data import WEB_DATA_DIR, dump_json, sanitize
from source.schemas.tracker import TrackerDataOutput, TrackerTracksOutput

logger = setup_logging(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # source/analysis
PORTS_OUTPUT_DIR = os.path.join(BASE_DIR, "ports", "output")

VISITS_FILE = os.path.join(PORTS_OUTPUT_DIR, "port_visits.jsonl")
VOYAGES_FILE = os.path.join(PORTS_OUTPUT_DIR, "voyages.jsonl")

DATA_JSON = WEB_DATA_DIR / "tracker_data.json"
TRACKS_JSON = WEB_DATA_DIR / "tracker_tracks.json"

# Tracker generation tuning
DAYS_BACK = 1000
TRACK_TIME_BUCKET = "10 minutes"
DB_POOL_MIN = 1
DB_POOL_MAX = 15
CHUNK_SIZE = 50
TRACK_MAX_WORKERS = 10
MAX_SPEED_KNOTS = 50.0
SIMPLIFY_TOLERANCE_M = 150.0
TOP_VESSELS_TANKER_CARGO = 4
TOP_VESSELS_OTHER = 2

db_pool: pool.ThreadedConnectionPool | None = None


def load_jsonl(path):
    if not os.path.exists(path):
        logger.warning(f"File not found: {path}")
        return []
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data


def process_vessel_chunk(chunk_mmsis, days_back=DAYS_BACK):
    local_tracks = {}
    assert db_pool is not None
    conn = db_pool.getconn()
    chunk_start = time.time()
    
    try:
        cur = conn.cursor()
        sql_start = time.time()
        
        query = f"""
            SELECT 
                mmsi,
                time_bucket('{TRACK_TIME_BUCKET}', timestamp) as bucket,
                ST_Y(last(position_geog, timestamp)::geometry) as lat,
                ST_X(last(position_geog, timestamp)::geometry) as lon,
                round(avg(speed_over_ground)::numeric, 1) as avg_sog,
                last(navigational_status, timestamp) as nav_status,
                last(destination, timestamp) as destination,
                last(draught_m, timestamp) as draught
            FROM ais_positions
            WHERE mmsi IN %s AND timestamp > now() - interval %s
            GROUP BY mmsi, bucket
            ORDER BY mmsi, bucket ASC
        """
        cur.execute(query, (tuple(chunk_mmsis), f"{days_back} days"))
        
        raw_rows = cur.fetchall()
        sql_time = time.time() - sql_start
        
        raw_data = defaultdict(list)
        for r in raw_rows:
            mmsi = str(r[0])
            raw_data[mmsi].append([
                r[2], r[3], r[1], float(r[4] or 0), 
                r[5] or "Unknown", r[6] or "None", float(r[7] or 0)
            ])
        
        logger.info(f"Chunk processed SQL: {len(raw_rows)} rows in {sql_time:.2f}s for {len(chunk_mmsis)} vessels.")
        
        proc_start = time.time()
        for mmsi, points in raw_data.items():
            n_raw = len(points)
            points = clean_trajectory(points, max_speed_knots=MAX_SPEED_KNOTS)
            if len(points) < 2:
                continue
            points = apply_median_filter(points)
            points = simplify_trajectory(points, tolerance_meters=SIMPLIFY_TOLERANCE_M)
            if len(points) >= 2:
                local_tracks[mmsi] = points
            
        proc_time = time.time() - proc_start
        logger.info(f"Chunk processed Logic: {len(local_tracks)} vessels in {proc_time:.2f}s (Total chunk time: {time.time() - chunk_start:.2f}s)")
            
        cur.close()
    except Exception as e:
        logger.error(f"Error processing chunk: {e}")
    finally:
        db_pool.putconn(conn)
    return local_tracks


def generate_tracker_data():
    global db_pool
    start_time = datetime.now()
    logger.info(f"Starting tracker data generation (Days: {DAYS_BACK})...")
    
    db_pool = pool.ThreadedConnectionPool(DB_POOL_MIN, DB_POOL_MAX, **connection_kwargs())
    
    visits = load_jsonl(VISITS_FILE)
    voyages = load_jsonl(VOYAGES_FILE)
    
    if not visits:
        logger.error("No visits found. Run port_visit_extractor first.")
        return

    activity_counts = defaultdict(int)
    mmsi_types = {}
    for v in visits:
        m = v['mmsi']
        activity_counts[m] += 1
        if m not in mmsi_types:
            mmsi_types[m] = v.get('ship_type', 'Unknown')
    
    for voy in voyages:
        activity_counts[voy['mmsi']] += 1
        if voy['mmsi'] not in mmsi_types:
            mmsi_types[voy['mmsi']] = 'Unknown'

    mmsis_by_type = defaultdict(list)
    for mmsi, count in activity_counts.items():
        s_type = mmsi_types.get(mmsi, 'Unknown')
        mmsis_by_type[s_type].append((mmsi, count))
    
    selected_pool = []
    for s_type in sorted(mmsis_by_type.keys()):
        limit_for_type = (
            TOP_VESSELS_TANKER_CARGO
            if s_type.lower() in ['tanker', 'cargo']
            else TOP_VESSELS_OTHER
        )
        
        sorted_mmsis = sorted(mmsis_by_type[s_type], key=lambda x: (-x[1], x[0]))
        top_for_type = [m for m, count in sorted_mmsis[:limit_for_type]]
        selected_pool.extend(top_for_type)
        logger.info(f"Selected top {len(top_for_type)} vessels for type: {s_type}")

    relevant_mmsis = sorted(selected_pool, key=lambda x: int(x) if str(x).isdigit() else 0, reverse=True)
    
    logger.info(f"Processing total of {len(relevant_mmsis)} vessels across {len(mmsis_by_type)} types (Sorted MMSI DESC).")

    visits_by_mmsi = defaultdict(list)
    for v in visits:
        if v['mmsi'] in relevant_mmsis:
            visits_by_mmsi[v['mmsi']].append(v)
        
    voyages_by_mmsi = defaultdict(list)
    for voy in voyages:
        if voy['mmsi'] in relevant_mmsis:
            voyages_by_mmsi[voy['mmsi']].append(voy)
        
    relevant_port_ids = list(set([v['port_id'] for m in relevant_mmsis for v in visits_by_mmsi[m]]))

    port_lookup = {}
    try:
        conn = db_pool.getconn()
        cur = conn.cursor()
        if relevant_port_ids:
            cur.execute("""
                SELECT id, name, un_locode, ST_Y(geom::geometry), ST_X(geom::geometry)
                FROM ports
                WHERE id IN %s
            """, (tuple(relevant_port_ids),))
            for r in cur.fetchall():
                port_lookup[r[0]] = {"name": r[1], "un_locode": r[2], "lat": r[3], "lon": r[4]}
        cur.close()
        db_pool.putconn(conn)
    except Exception as e:
        logger.error(f"Failed to fetch ports: {e}")

    data_payload = {
        "visits": visits_by_mmsi,
        "voyages": voyages_by_mmsi,
        "ports": port_lookup,
        "sample_mmsis": [str(m) for m in relevant_mmsis],
    }
    tracker_data = TrackerDataOutput.model_validate(sanitize(data_payload))
    dump_json(DATA_JSON, tracker_data.model_dump(mode="json"))
    logger.info("Saved %s", DATA_JSON)

    mmsi_chunks = [relevant_mmsis[i:i + CHUNK_SIZE] for i in range(0, len(relevant_mmsis), CHUNK_SIZE)]

    tracks_payload = {}
    logger.info(
        f"Processing tracks for {len(relevant_mmsis)} vessels using ThreadPoolExecutor "
        f"({TRACK_MAX_WORKERS} workers)..."
    )

    with ThreadPoolExecutor(max_workers=TRACK_MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_vessel_chunk, chunk, DAYS_BACK): i
            for i, chunk in enumerate(mmsi_chunks)
        }

        completed = 0
        for future in as_completed(futures):
            chunk_data = future.result()
            tracks_payload.update(chunk_data)
            completed += 1
            logger.info(f"Progress: {completed}/{len(mmsi_chunks)} chunks processed.")

    tracker_tracks = TrackerTracksOutput.model_validate(sanitize(tracks_payload))
    dump_json(TRACKS_JSON, tracker_tracks.model_dump(mode="json"))

    db_pool.closeall()

    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()

    logger.info("Saved %s (Tracks for %s vessels)", TRACKS_JSON, len(tracks_payload))
    logger.info(f"Done! Total time: {elapsed:.2f}s")

if __name__ == "__main__":
    generate_tracker_data()
