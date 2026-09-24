from typing import List
from dataclasses import dataclass

@dataclass(frozen=True)
class AISPositionsColumns:
    """Columns matching the ais_positions table in PostgreSQL."""
    TIMESTAMP: str = "timestamp"
    TYPE_OF_MOBILE: str = "type_of_mobile"
    MMSI: str = "mmsi"
    LATITUDE: str = "latitude"
    LONGITUDE: str = "longitude"
    NAV_STATUS: str = "navigational_status"
    ROT: str = "rate_of_turn"
    SOG: str = "speed_over_ground"
    COG: str = "course_over_ground"
    HEADING: str = "heading"
    IMO: str = "imo"
    CALLSIGN: str = "callsign"
    NAME: str = "name"
    SHIP_TYPE: str = "ship_type"
    CARGO_TYPE: str = "cargo_type"
    WIDTH_M: str = "width_m"
    LENGTH_M: str = "length_m"
    POS_FIX: str = "position_fixing_device_type"
    DRAUGHT_M: str = "draught_m"
    DESTINATION: str = "destination"
    ETA: str = "eta"
    DATA_SOURCE_TYPE: str = "data_source_type"
    SIZE_A_M: str = "size_a_m"
    SIZE_B_M: str = "size_b_m"
    SIZE_C_M: str = "size_c_m"
    SIZE_D_M: str = "size_d_m"
    POSITION_GEOG: str = "position_geog"
    CREATED_AT: str = "created_at"

    def all(self) -> List[str]:
        return [v for k, v in self.__dict__.items()]

    def pg_dtype_map(self) -> dict[str,str]:
        return {
            self.TIMESTAMP: "TIMESTAMPTZ",
            self.TYPE_OF_MOBILE: "TEXT",
            self.MMSI: "BIGINT",
            self.LATITUDE: "DOUBLE PRECISION",
            self.LONGITUDE: "DOUBLE PRECISION",
            self.NAV_STATUS: "TEXT",
            self.ROT: "DOUBLE PRECISION",
            self.SOG: "DOUBLE PRECISION",
            self.COG: "DOUBLE PRECISION",
            self.HEADING: "DOUBLE PRECISION",
            self.IMO: "TEXT",
            self.CALLSIGN: "TEXT",
            self.NAME: "TEXT",
            self.SHIP_TYPE: "TEXT",
            self.CARGO_TYPE: "TEXT",
            self.WIDTH_M: "DOUBLE PRECISION",
            self.LENGTH_M: "DOUBLE PRECISION",
            self.POS_FIX: "TEXT",
            self.DRAUGHT_M: "DOUBLE PRECISION",
            self.DESTINATION: "TEXT",
            self.ETA: "TIMESTAMPTZ",
            self.DATA_SOURCE_TYPE: "TEXT",
            self.SIZE_A_M: "DOUBLE PRECISION",
            self.SIZE_B_M: "DOUBLE PRECISION",
            self.SIZE_C_M: "DOUBLE PRECISION",
            self.SIZE_D_M: "DOUBLE PRECISION",
            self.POSITION_GEOG: "GEOGRAPHY(Point,4326)",
            self.CREATED_AT: "TIMESTAMPTZ",
        }
