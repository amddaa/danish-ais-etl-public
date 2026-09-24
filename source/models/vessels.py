from typing import List
from dataclasses import dataclass

@dataclass(frozen=True)
class VesselsColumns:
    """Columns matching the vessels table in PostgreSQL."""
    MMSI: str = "mmsi"
    IMO: str = "imo"
    CALLSIGN: str = "callsign"
    NAME: str = "name"
    SHIP_TYPE: str = "ship_type"
    CARGO_TYPE: str = "cargo_type"
    WIDTH_M: str = "width_m"
    LENGTH_M: str = "length_m"
    POS_FIX: str = "position_fixing_device_type"
    LAST_KNOWN_DRAUGHT_M: str = "last_known_draught_m"
    FIRST_SEEN_AT: str = "first_seen_at"
    LAST_SEEN_AT: str = "last_seen_at"

    def all(self) -> List[str]:
        return [v for k, v in self.__dict__.items()]
    
    def pg_dtype_map(self) -> dict[str,str]:
        return {
            self.MMSI: "BIGINT",
            self.IMO: "TEXT",
            self.CALLSIGN: "TEXT",
            self.NAME: "TEXT",
            self.SHIP_TYPE: "TEXT",
            self.CARGO_TYPE: "TEXT",
            self.WIDTH_M: "DOUBLE PRECISION",
            self.LENGTH_M: "DOUBLE PRECISION",
            self.POS_FIX: "TEXT",
            self.LAST_KNOWN_DRAUGHT_M: "DOUBLE PRECISION",
            self.FIRST_SEEN_AT: "TIMESTAMPTZ",
            self.LAST_SEEN_AT: "TIMESTAMPTZ",
        }
