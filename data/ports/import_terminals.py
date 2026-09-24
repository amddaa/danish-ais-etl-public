from __future__ import annotations

import json
import os
import sys

from source.config.db import get_db_connection
from source.config.logger import setup_logging

GEOJSON_PATH = os.path.join(os.path.dirname(__file__), "baltic_ports.geojson")

logger = setup_logging(__name__)


def import_terminals(geojson_path: str = GEOJSON_PATH) -> None:
    if not os.path.exists(geojson_path):
        logger.error("Terminal GeoJSON not found: %s", geojson_path)
        sys.exit(1)

    logger.info("Loading terminals from %s into port_terminals...", geojson_path)
    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = get_db_connection(connect_timeout=10)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM port_terminals")
            count = cur.fetchone()[0]
            if count > 0:
                logger.info(
                    "port_terminals already has %d rows; skipping import to avoid duplicates.",
                    count,
                )
                return

            inserted = 0
            for feat in data.get("features", []):
                props = feat.get("properties") or {}
                geom = feat.get("geometry") or {}
                coords = geom.get("coordinates")
                if not coords or len(coords) < 2:
                    continue

                name = props.get("name") or props.get("name:en") or "Unknown"
                lon, lat = coords[0], coords[1]
                cur.execute(
                    """
                    INSERT INTO port_terminals (name, geom)
                    VALUES (%s, ST_SetSRID(ST_Point(%s, %s), 4326)::geography)
                    """,
                    (name, lon, lat),
                )
                inserted += 1

            conn.commit()
            logger.info(
                "Imported %d terminals into port_terminals (for map visualization; "
                "run spatial_link_wpi.py after import_wpi.py to set port_id).",
                inserted,
            )
    except Exception:
        conn.rollback()
        logger.exception("Terminal import failed")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import_terminals()
