"""Nearest-neighbour link of port_terminals to WPI ports within LINK_RADIUS_M."""

import os
import sys

from source.config.db import get_db_connection
from source.config.logger import setup_logging

LINK_RADIUS_M = 10_000

logger = setup_logging(__name__)


def run_spatial_link() -> None:
    conn = get_db_connection(connect_timeout=10)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM port_terminals WHERE port_id IS NULL")
    total = cur.fetchone()[0]
    logger.info("Found %d port_terminals without a parent port.", total)

    if total == 0:
        logger.info("All terminals already linked. Nothing to do.")
        cur.close()
        conn.close()
        return

    # Bulk nearest-neighbour UPDATE via LATERAL join
    update_sql = f"""
        UPDATE port_terminals AS t
        SET port_id = nearest.wpi_id
        FROM (
            SELECT
                t2.id AS terminal_id,
                closest.id AS wpi_id
            FROM port_terminals t2
            CROSS JOIN LATERAL (
                SELECT p.id
                FROM ports p
                WHERE ST_DWithin(t2.geom, p.geom, {LINK_RADIUS_M})
                ORDER BY t2.geom <-> p.geom
                LIMIT 1
            ) closest
            WHERE t2.port_id IS NULL
        ) nearest
        WHERE t.id = nearest.terminal_id
    """

    cur.execute(update_sql)
    linked = cur.rowcount
    conn.commit()
    logger.info("Linked %d terminals to a parent WPI port.", linked)

    cur.execute(
        "SELECT id, name FROM port_terminals WHERE port_id IS NULL ORDER BY id"
    )
    unlinked = cur.fetchall()

    if unlinked:
        logger.warning(
            "%d terminals could NOT be linked (no WPI port within %d m):",
            len(unlinked), LINK_RADIUS_M,
        )
        for tid, tname in unlinked:
            logger.warning("  terminal_id=%d  name='%s'", tid, tname)
    else:
        logger.info("All terminals successfully linked.")

    cur.execute("""
        SELECT
            p.un_locode,
            p.name,
            COUNT(t.id) AS terminal_count
        FROM ports p
        JOIN port_terminals t ON t.port_id = p.id
        GROUP BY p.id
        ORDER BY terminal_count DESC
        LIMIT 20
    """)
    rows = cur.fetchall()
    logger.info("Top 20 WPI ports by terminal count:")
    for locode, name, cnt in rows:
        logger.info("  %-6s  %-40s  %d terminal(s)", locode or "N/A", name, cnt)

    cur.close()
    conn.close()


if __name__ == "__main__":
    run_spatial_link()
