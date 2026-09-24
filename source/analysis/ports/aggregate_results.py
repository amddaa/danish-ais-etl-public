import json
import os
from datetime import datetime, timezone
from collections import defaultdict
from typing import Any
import numpy as np

from source.config.db import get_db_connection
from source.config.logger import setup_logging

logger = setup_logging(__name__)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
VISITS_FILE = os.path.join(OUTPUT_DIR, "port_visits.jsonl")
VOYAGES_FILE = os.path.join(OUTPUT_DIR, "voyages.jsonl")
GEOFENCES_FILE = os.path.join(OUTPUT_DIR, "port_geofences.json")

UI_OUTPUT_FILE = os.path.join("source", "analysis", "routes", "route_analysis_results.json")

def load_jsonl(path: str) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = []
    if not os.path.exists(path):
        return data
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data

def aggregate_stats():
    logger.info("Starting result aggregation for UI...")
    
    visits = load_jsonl(VISITS_FILE)
    voyages = load_jsonl(VOYAGES_FILE)
    
    if not visits and not voyages:
        logger.warning("No visits or voyages found to aggregate!")
        return

    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT id, name, ST_X(geom::geometry), ST_Y(geom::geometry) FROM ports")
    port_meta = {r[0]: {"name": r[1], "lon": r[2], "lat": r[3]} for r in cur.fetchall()}
    
    cur.execute("SELECT mmsi, name FROM vessels")
    vessel_names = {r[0]: r[1] for r in cur.fetchall()}
    conn.close()

    routes_agg: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "trips": [], 
        "vessels": defaultdict(list),
        "draughts": []
    })

    for v in voyages:
        rid = f"{v['origin_port_id']}_{v['destination_port_id']}"
        routes_agg[rid]["trips"].append(v)
        routes_agg[rid]["vessels"][v["mmsi"]].append(v)
        if v["draught_at_dest_m"]:
            routes_agg[rid]["draughts"].append(v["draught_at_dest_m"])

    ui_routes: list[dict[str, Any]] = []
    total_trips = 0
    unique_vessels: set[Any] = set()
    unique_ports: set[Any] = set()

    for rid, data in routes_agg.items():
        origin_id, dest_id = map(int, rid.split("_"))
        
        # Skip if ports missing in metadata
        if origin_id not in port_meta or dest_id not in port_meta:
            continue
            
        unique_ports.add(origin_id)
        unique_ports.add(dest_id)
        
        vessels_list: list[dict[str, Any]] = []
        for mmsi, v_voyages in data["vessels"].items():
            unique_vessels.add(mmsi)
            v_draughts = [v["draught_at_dest_m"] for v in v_voyages if v["draught_at_dest_m"]]
            
            vessels_list.append({
                "mmsi": mmsi,
                "name": vessel_names.get(mmsi, f"MMSI {mmsi}"),
                "ship_type": v_voyages[0]["ship_type"],
                "trip_count": len(v_voyages),
                "draught_stats": {
                    "min": round(min(v_draughts), 2) if v_draughts else 0,
                    "avg": round(np.mean(v_draughts), 2) if v_draughts else 0,
                    "max": round(max(v_draughts), 2) if v_draughts else 0
                }
            })
        
        # Sort vessels by trip count
        vessels_list.sort(key=lambda x: int(x["trip_count"]), reverse=True)
        
        route_trips = len(data["trips"])
        total_trips += route_trips
        
        ui_routes.append({
            "route_id": rid,
            "origin": {
                "port_id": origin_id,
                "name": port_meta[origin_id]["name"],
                "geometry": {"type": "Point", "coordinates": [port_meta[origin_id]["lon"], port_meta[origin_id]["lat"]]}
            },
            "destination": {
                "port_id": dest_id,
                "name": port_meta[dest_id]["name"],
                "geometry": {"type": "Point", "coordinates": [port_meta[dest_id]["lon"], port_meta[dest_id]["lat"]]}
            },
            "total_trips": route_trips,
            "draught_stats": {
                "min": round(min(data["draughts"]), 2) if data["draughts"] else 0,
                "avg": round(np.mean(data["draughts"]), 2) if data["draughts"] else 0,
                "max": round(max(data["draughts"]), 2) if data["draughts"] else 0
            },
            "vessels": vessels_list
        })

    ui_ports: list[dict[str, Any]] = []
    port_agg: dict[Any, dict[str, Any]] = defaultdict(lambda: {"visits": 0, "draughts": []})
    for r in ui_routes:
        oid = r["origin"]["port_id"]
        port_agg[oid]["visits"] += r["total_trips"]
        if r["draught_stats"]["max"] > 0:
            port_agg[oid]["draughts"].append(r["draught_stats"]["max"])
            
    for pid in unique_ports:
        stats = port_agg.get(pid, {"visits": 0, "draughts": []})
        ui_ports.append({
            "port_id": pid,
            "name": port_meta[pid]["name"],
            "total_visits": stats["visits"],
            "geometry": {"type": "Point", "coordinates": [port_meta[pid]["lon"], port_meta[pid]["lat"]]},
            "draught_stats": {
                "min": round(min(stats["draughts"]), 2) if stats["draughts"] else 0,
                "avg": round(np.mean(stats["draughts"]), 2) if stats["draughts"] else 0,
                "max": round(max(stats["draughts"]), 2) if stats["draughts"] else 0
            }
        })

    ui_vessels: list[dict[str, Any]] = []
    vessel_agg: dict[Any, dict[str, Any]] = defaultdict(lambda: {"trips": 0, "draughts": [], "name": "", "type": ""})
    for r in ui_routes:
        for v in r["vessels"]:
            vid = v["mmsi"]
            vessel_agg[vid]["trips"] += v["trip_count"]
            vessel_agg[vid]["draughts"].append(v["draught_stats"]["max"])
            vessel_agg[vid]["name"] = v["name"]
            vessel_agg[vid]["type"] = v["ship_type"]

    for mmsi, vdata in vessel_agg.items():
        ui_vessels.append({
            "mmsi": mmsi,
            "name": vdata["name"],
            "ship_type": vdata["type"],
            "total_trips": vdata["trips"],
            "draught_stats": {
                "min": round(min(vdata["draughts"]), 2) if vdata["draughts"] else 0,
                "avg": round(np.mean(vdata["draughts"]), 2) if vdata["draughts"] else 0,
                "max": round(max(vdata["draughts"]), 2) if vdata["draughts"] else 0
            }
        })

    final_output = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_routes": len(ui_routes),
            "total_ports": len(unique_ports),
            "total_vessels": len(unique_vessels),
            "total_trips": total_trips,
            "engine": "State Machine v2"
        },
        "routes": ui_routes,
        "ports": ui_ports,
        "vessels": ui_vessels
    }

    os.makedirs(os.path.dirname(UI_OUTPUT_FILE), exist_ok=True)
    with open(UI_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2)
    
    logger.info(f"UI aggregation complete. Saved {len(ui_routes)} routes to {UI_OUTPUT_FILE}")

if __name__ == "__main__":
    aggregate_stats()
