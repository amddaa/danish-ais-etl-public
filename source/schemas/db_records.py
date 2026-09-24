from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class PortVisitRecord(BaseModel):
    """One row from the port_visits table."""
    id: Optional[int] = None
    mmsi: int
    port_id: int
    arrival_time: datetime
    departure_time: Optional[datetime] = None
    stay_duration_hours: Optional[float] = None
    draught_m: Optional[float] = None
    ship_type: Optional[str] = None
    cargo_type: Optional[str] = None
    length_m: Optional[float] = None
    width_m: Optional[float] = None
    declared_destination: Optional[str] = None
    n_positions: Optional[int] = None
    created_at: Optional[datetime] = None

class PortRecord(BaseModel):
    """One row from the ports (WPI) table."""
    id: int
    wpi_number: Optional[int] = None
    name: str
    un_locode: Optional[str] = None
    country_code: Optional[str] = None
    region_name: Optional[str] = None
    longitude: float
    latitude: float
    harbor_size: Optional[str] = None
    harbor_type: Optional[str] = None
    max_vessel_draft_m: Optional[float] = None

class VesselRecord(BaseModel):
    """One row from the vessels table."""
    mmsi: int
    imo: Optional[str] = None
    callsign: Optional[str] = None
    name: Optional[str] = None
    ship_type: Optional[str] = None
    cargo_type: Optional[str] = None
    width_m: Optional[float] = None
    length_m: Optional[float] = None
    last_known_draught_m: Optional[float] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
