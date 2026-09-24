from typing import List
from dataclasses import dataclass

@dataclass(frozen=True)
class PortVisitsColumns:
    """Columns matching the port_visits table in PostgreSQL (06_create_port_visits.sql)."""
    ID: str = "id"
    MMSI: str = "mmsi"
    PORT_ID: str = "port_id"
    ARRIVAL_TIME: str = "arrival_time"
    DEPARTURE_TIME: str = "departure_time"
    STAY_DURATION_HOURS: str = "stay_duration_hours"   
    DRAUGHT_M: str = "draught_m"
    SHIP_TYPE: str = "ship_type"
    CARGO_TYPE: str = "cargo_type"
    LENGTH_M: str = "length_m"
    WIDTH_M: str = "width_m"
    DECLARED_DESTINATION: str = "declared_destination"
    N_POSITIONS: str = "n_positions"
    CREATED_AT: str = "created_at"

    def all(self) -> List[str]:
        return [v for k, v in self.__dict__.items()]

    def pg_dtype_map(self) -> dict[str, str]:
        return {
            self.ID: "BIGINT",
            self.MMSI: "BIGINT",
            self.PORT_ID: "INTEGER",
            self.ARRIVAL_TIME: "TIMESTAMPTZ",
            self.DEPARTURE_TIME: "TIMESTAMPTZ",
            self.STAY_DURATION_HOURS: "DOUBLE PRECISION",
            self.DRAUGHT_M: "DOUBLE PRECISION",
            self.SHIP_TYPE: "TEXT",
            self.CARGO_TYPE: "TEXT",
            self.LENGTH_M: "DOUBLE PRECISION",
            self.WIDTH_M: "DOUBLE PRECISION",
            self.DECLARED_DESTINATION: "TEXT",
            self.N_POSITIONS: "INTEGER",
            self.CREATED_AT: "TIMESTAMPTZ",
        }
