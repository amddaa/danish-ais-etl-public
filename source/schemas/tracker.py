from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, RootModel


class TrackerPort(BaseModel):
    name: str
    un_locode: Optional[str] = None
    lat: float
    lon: float


class TrackerVisit(BaseModel):
    model_config = ConfigDict(extra="allow")

    port_id: int
    arrival_time: str
    departure_time: Optional[str] = None
    stay_duration_hours: Optional[float] = None
    draught_m: Optional[float] = None
    length_m: Optional[float] = None
    width_m: Optional[float] = None
    n_positions: Optional[int] = None
    ship_type: Optional[str] = None
    declared_destination: Optional[str] = None


class TrackerVoyage(BaseModel):
    model_config = ConfigDict(extra="allow")

    origin_port_id: int
    destination_port_id: int
    voyage_duration_hours: float
    draught_at_origin_m: Optional[float] = None
    draught_at_dest_m: Optional[float] = None
    ship_type: Optional[str] = None
    cargo_type: Optional[str] = None
    declared_destination: Optional[str] = None


class TrackerDataOutput(BaseModel):
    """Full payload for web/src/data/tracker_data.json."""

    visits: Dict[str, List[TrackerVisit]]
    voyages: Dict[str, List[TrackerVoyage]]
    ports: Dict[str, TrackerPort]
    sample_mmsis: List[str]


class TrackerTracksOutput(RootModel[Dict[str, List[List[Any]]]]):
    """Full payload for web/src/data/tracker_tracks.json.

    Each track is a list of [lat, lon, ISO timestamp, sog, nav status, destination, draught].
    """


class RouteMapStats(BaseModel):
    """Payload for web/src/data/routes_map/stats.json."""

    routes: int
    ports: int
    vessels: int
    trips: int
