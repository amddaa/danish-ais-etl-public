from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class VoyageRecord(BaseModel):
    """
    A single voyage (leg) between two consecutive port visits for one vessel.
    Derived in-memory from paired PortVisitRecords.
    """
    mmsi: int
    ship_type: Optional[str] = None
    cargo_type: Optional[str] = None
    origin_port_id: int
    destination_port_id: int
    departure_time: datetime             # = departure_time of origin visit
    arrival_time: datetime               # = arrival_time of destination visit
    voyage_duration_hours: float         # time at sea
    draught_at_origin_m: Optional[float] = None
    draught_at_dest_m: Optional[float] = None
    declared_destination: Optional[str] = None

class ExtractionMetadata(BaseModel):
    """Metadata for the extraction process."""
    generated_at: datetime
    total_visits: int
    total_voyages: int
    n_vessels_processed: int
