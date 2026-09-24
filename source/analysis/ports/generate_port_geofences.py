from datetime import timezone
from datetime import datetime
import json
import os
from source.config.db import get_db_connection
from source.config.logger import setup_logging

logger = setup_logging(__name__)

BUFFER_NM = 1.5 
METERS_PER_NM = 1852
BUFFER_METERS = BUFFER_NM * METERS_PER_NM

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "port_geofences.json")

def generate_geofences():
    logger.info(f"Generating Port Geofences with {BUFFER_NM} NM buffer...")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Query to build buffered convex hulls for each WPI port
        # We collect the WPI center point and all its terminal points
        query = """
            WITH PortPoints AS (
                -- Collect WPI center
                SELECT id, name, wpi_number, un_locode, geom::geometry as pt
                FROM ports
                UNION ALL
                -- Collect all linked terminals
                SELECT p.id, p.name, p.wpi_number, p.un_locode, t.geom::geometry as pt
                FROM ports p
                JOIN port_terminals t ON t.port_id = p.id
            ),
            PortHulls AS (
                SELECT 
                    id, name, wpi_number, un_locode,
                    ST_ConvexHull(ST_Collect(pt)) as hull
                FROM PortPoints
                GROUP BY id, name, wpi_number, un_locode
            )
            SELECT 
                id, name, wpi_number, un_locode,
                ST_AsGeoJSON(ST_Buffer(hull::geography, %s)::geometry) as geojson,
                ST_Area(ST_Buffer(hull::geography, %s)) / 1000000.0 as area_sq_km,
                (SELECT count(*) FROM port_terminals WHERE port_id = PortHulls.id) as terminal_count,
                -- Additional Metadata for popups
                (SELECT country_code FROM ports WHERE id = PortHulls.id) as country_code,
                (SELECT harbor_size FROM ports WHERE id = PortHulls.id) as harbor_size,
                (SELECT harbor_type FROM ports WHERE id = PortHulls.id) as harbor_type,
                (SELECT vessel_traffic_service FROM ports WHERE id = PortHulls.id) as vts,
                (SELECT max_vessel_draft_m FROM ports WHERE id = PortHulls.id) as max_draft
            FROM PortHulls;
        """
        
        cur.execute(query, (BUFFER_METERS, BUFFER_METERS))
        rows = cur.fetchall()
        
        features = []
        for r in rows:
            pid, name, wpi, locode, geojson_str, area, t_count, country, h_size, h_type, vts, max_draft = r
            geom = json.loads(geojson_str)
            
            features.append({
                "type": "Feature",
                "properties": {
                    "port_id": pid,
                    "name": name,
                    "wpi_number": wpi,
                    "un_locode": locode,
                    "area_sq_km": round(area, 2),
                    "terminal_count": t_count,
                    "buffer_nm": BUFFER_NM,
                    "country_code": country,
                    "harbor_size": h_size,
                    "harbor_type": h_type,
                    "vessel_traffic_service": vts,
                    "max_vessel_draft_m": max_draft
                },
                "geometry": geom
            })
            
        output = {
            "type": "FeatureCollection",
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "buffer_nm": BUFFER_NM,
                "total_ports": len(features)
            },
            "features": features
        }
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
            
        logger.info(f"Successfully generated {len(features)} geofences to {OUTPUT_FILE}")
        
    except Exception as e:
        import traceback
        logger.error(f"Failed to generate geofences: {e}\n{traceback.format_exc()}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    generate_geofences()
