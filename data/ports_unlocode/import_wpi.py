"""Import UpdatedPub150.csv (WPI / Pub 150) into the ports table."""

from __future__ import annotations

import csv
import os
import sys
from typing import Any

import psycopg2.extras

from source.config.db import get_db_connection
from source.config.logger import setup_logging

CSV_PATH = os.path.join(os.path.dirname(__file__), "UpdatedPub150.csv")

logger = setup_logging(__name__)

# Yes/No/Unknown stored as TEXT; empty numeric → None; 0.0 depth/dim → None (WPI sentinel)
NUMERIC_COLUMNS = {
    "World Port Index Number",
    "Tidal Range (m)",
    "Entrance Width (m)",
    "Channel Depth (m)",
    "Anchorage Depth (m)",
    "Cargo Pier Depth (m)",
    "Oil Terminal Depth (m)",
    "Liquified Natural Gas Terminal Depth (m)",
    "Maximum Vessel Length (m)",
    "Maximum Vessel Beam (m)",
    "Maximum Vessel Draft (m)",
    "Offshore Maximum Vessel Length (m)",
    "Offshore Maximum Vessel Beam (m)",
    "Offshore Maximum Vessel Draft (m)",
    "Latitude",
    "Longitude",
}

COLUMN_MAP = {
    "World Port Index Number": "wpi_number",
    "Main Port Name": "name",
    "Alternate Port Name": "name_alternate",
    "UN/LOCODE": "un_locode",
    "Country Code": "country_code",
    "Region Name": "region_name",
    "World Water Body": "world_water_body",
    "IHO S-130 Sea Area": "iho_sea_area",
    "Tidal Range (m)": "tidal_range_m",
    "Entrance Width (m)": "entrance_width_m",
    "Channel Depth (m)": "channel_depth_m",
    "Anchorage Depth (m)": "anchorage_depth_m",
    "Cargo Pier Depth (m)": "cargo_pier_depth_m",
    "Oil Terminal Depth (m)": "oil_terminal_depth_m",
    "Liquified Natural Gas Terminal Depth (m)": "lng_terminal_depth_m",
    "Maximum Vessel Length (m)": "max_vessel_length_m",
    "Maximum Vessel Beam (m)": "max_vessel_beam_m",
    "Maximum Vessel Draft (m)": "max_vessel_draft_m",
    "Offshore Maximum Vessel Length (m)": "offshore_max_vessel_length_m",
    "Offshore Maximum Vessel Beam (m)": "offshore_max_vessel_beam_m",
    "Offshore Maximum Vessel Draft (m)": "offshore_max_vessel_draft_m",
    "Harbor Size": "harbor_size",
    "Harbor Type": "harbor_type",
    "Harbor Use": "harbor_use",
    "Shelter Afforded": "shelter_afforded",
    "Entrance Restriction - Tide": "restriction_tide",
    "Entrance Restriction - Heavy Swell": "restriction_heavy_swell",
    "Entrance Restriction - Ice": "restriction_ice",
    "Entrance Restriction - Other": "restriction_other",
    "Overhead Limits": "overhead_limits",
    "Underkeel Clearance Management System": "underkeel_clearance_system",
    "Good Holding Ground": "good_holding_ground",
    "Turning Area": "turning_area",
    "Port Security": "port_security",
    "Traffic Separation Scheme": "traffic_separation_scheme",
    "Vessel Traffic Service": "vessel_traffic_service",
    "NAVAREA": "navarea",
    "First Port of Entry": "first_port_of_entry",
    "Estimated Time of Arrival Message": "eta_message",
    "Quarantine - Pratique": "quarantine_pratique",
    "Quarantine - Sanitation": "quarantine_sanitation",
    "Quarantine - Other": "quarantine_other",
    "Pilotage - Compulsory": "pilotage_compulsory",
    "Pilotage - Available": "pilotage_available",
    "Pilotage - Local Assistance": "pilotage_local_assistance",
    "Pilotage - Advisable": "pilotage_advisable",
    "Tugs - Salvage": "tugs_salvage",
    "Tugs - Assistance": "tugs_assistance",
    "Communications - Telephone": "comm_telephone",
    "Communications - Telefax": "comm_telefax",
    "Communications - Radio": "comm_radio",
    "Communications - Radiotelephone": "comm_radiotelephone",
    "Communications - Airport": "comm_airport",
    "Communications - Rail": "comm_rail",
    "Search and Rescue": "search_and_rescue",
    "Facilities - Wharves": "facility_wharves",
    "Facilities - Anchorage": "facility_anchorage",
    "Facilities - Dangerous Cargo Anchorage": "facility_dangerous_cargo_anchor",
    "Facilities - Med Mooring": "facility_med_mooring",
    "Facilities - Beach Mooring": "facility_beach_mooring",
    "Facilities - Ice Mooring": "facility_ice_mooring",
    "Facilities - Ro-Ro": "facility_ro_ro",
    "Facilities - Solid Bulk": "facility_solid_bulk",
    "Facilities - Liquid Bulk": "facility_liquid_bulk",
    "Facilities - Container": "facility_container",
    "Facilities - Breakbulk": "facility_breakbulk",
    "Facilities - Oil Terminal": "facility_oil_terminal",
    "Facilities - LNG Terminal": "facility_lng_terminal",
    "Facilities - Other": "facility_other",
    "Medical Facilities": "medical_facilities",
    "Garbage Disposal": "garbage_disposal",
    "Chemical Holding Tank Disposal": "chemical_holding_tank_disposal",
    "Degaussing": "degaussing",
    "Dirty Ballast Disposal": "dirty_ballast_disposal",
    "Cranes - Fixed": "cranes_fixed",
    "Cranes - Mobile": "cranes_mobile",
    "Cranes - Floating": "cranes_floating",
    "Cranes Container": "cranes_container",
    "Lifts - 100+ Tons": "lifts_100plus_tons",
    "Lifts - 50-100 Tons": "lifts_50_100_tons",
    "Lifts - 25-49 Tons": "lifts_25_49_tons",
    "Lifts - 0-24 Tons": "lifts_0_24_tons",
    "Services - Longshoremen": "services_longshoremen",
    "Services - Electricity": "services_electricity",
    "Services -Steam": "services_steam",
    "Services - Navigation Equipment": "services_navigation_equipment",
    "Services - Electrical Repair": "services_electrical_repair",
    "Services - Ice Breaking": "services_ice_breaking",
    "Services -Diving": "services_diving",
    "Supplies - Provisions": "supplies_provisions",
    "Supplies - Potable Water": "supplies_potable_water",
    "Supplies - Fuel Oil": "supplies_fuel_oil",
    "Supplies - Diesel Oil": "supplies_diesel_oil",
    "Supplies - Aviation Fuel": "supplies_aviation_fuel",
    "Supplies - Deck": "supplies_deck",
    "Supplies - Engine": "supplies_engine",
    "Repairs": "repairs",
    "Dry Dock": "dry_dock",
    "Railway": "railway",
}

SKIP_COLUMNS = {
    "OID_",
    "Sailing Direction or Publication",
    "Publication Link",
    "Standard Nautical Chart",
    "IHO S-57 Electronic Navigational Chart",
    "IHO S-101 Electronic Navigational Chart",
    "Digital Nautical Chart",
    "US Representative",
}


def parse_value(col_name: str, raw: str) -> float | str | None:
    """Coerce a raw CSV string into the appropriate Python type."""
    raw = raw.strip()
    if not raw:
        return None

    if col_name in NUMERIC_COLUMNS:
        try:
            val = float(raw)
            if col_name not in {"Latitude", "Longitude"} and val == 0.0:
                return None
            return val
        except ValueError:
            logger.warning("Cannot parse numeric '%s' for column '%s'", raw, col_name)
            return None

    return raw


def build_insert_sql(db_columns: list[str]) -> str:
    """INSERT … ON CONFLICT (wpi_number) DO NOTHING; geom from lon/lat."""
    cols = db_columns + ["geom"]
    placeholders = [
        f"%({c})s" if c != "geom" else
        "ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326)::geography"
        for c in cols
    ]
    return (
        f"INSERT INTO ports ({', '.join(cols)}) "
        f"VALUES ({', '.join(placeholders)}) "
        f"ON CONFLICT (wpi_number) DO NOTHING"
    )


def import_wpi(csv_path: str = CSV_PATH, batch_size: int = 500) -> None:
    if not os.path.exists(csv_path):
        logger.error("CSV file not found: %s", csv_path)
        sys.exit(1)

    conn = get_db_connection(connect_timeout=10)
    cur = conn.cursor()

    cur.execute("SELECT to_regclass('public.ports')")
    if cur.fetchone()[0] is None:
        logger.error(
            "Table 'ports' does not exist. "
            "Please run migration 07_refactor_ports_to_wpi.sql first."
        )
        conn.close()
        sys.exit(1)

    inserted = 0
    skipped = 0
    batch: list[dict[str, Any]] = []

    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        if not fieldnames:
            logger.error("CSV has no header row: %s", csv_path)
            conn.close()
            sys.exit(1)

        db_columns = [
            COLUMN_MAP[h]
            for h in fieldnames
            if h in COLUMN_MAP and h not in {"Latitude", "Longitude"}
        ]
        insert_sql = build_insert_sql(db_columns)

        for row_idx, row in enumerate(reader, start=2):
            if not row.get("Main Port Name", "").strip():
                skipped += 1
                continue

            lat = parse_value("Latitude", row.get("Latitude", "") or "")
            lon = parse_value("Longitude", row.get("Longitude", "") or "")
            if lat is None or lon is None:
                logger.debug("Row %d: missing coordinates, skipping.", row_idx)
                skipped += 1
                continue

            record: dict[str, Any] = {"latitude": lat, "longitude": lon}
            for csv_col, db_col in COLUMN_MAP.items():
                if csv_col in {"Latitude", "Longitude"}:
                    continue
                record[db_col] = parse_value(csv_col, row.get(csv_col, "") or "")

            un_locode = record.get("un_locode")
            if isinstance(un_locode, str):
                record["un_locode"] = un_locode.strip() or None

            batch.append(record)

            if len(batch) >= batch_size:
                psycopg2.extras.execute_batch(cur, insert_sql, batch)
                conn.commit()
                inserted += len(batch)
                logger.info("Inserted %d rows so far…", inserted)
                batch.clear()

    if batch:
        psycopg2.extras.execute_batch(cur, insert_sql, batch)
        conn.commit()
        inserted += len(batch)

    cur.close()
    conn.close()

    logger.info("Import complete: %d rows inserted, %d rows skipped.", inserted, skipped)


if __name__ == "__main__":
    import_wpi()
