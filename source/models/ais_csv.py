from typing import List
from dataclasses import dataclass

@dataclass(frozen=True)
class AISColumnsCSV:
    """Columns as they appear in the AIS CSV file."""
    TIMESTAMP: str = "# Timestamp" 
    TYPE_OF_MOBILE: str = "Type of mobile" 
    MMSI: str = "MMSI" 
    LATITUDE: str = "Latitude" 
    LONGITUDE: str = "Longitude" 
    NAV_STATUS: str = "Navigational status" 
    ROT: str = "ROT" 
    SOG: str = "SOG" 
    COG: str = "COG" 
    HEADING: str = "Heading" 
    IMO: str = "IMO" 
    CALLSIGN: str = "Callsign" 
    NAME: str = "Name" 
    SHIP_TYPE: str = "Ship type" 
    CARGO_TYPE: str = "Cargo type" 
    WIDTH: str = "Width" 
    LENGTH: str = "Length" 
    POS_FIX: str = "Type of position fixing device"  
    DRAUGHT: str = "Draught" 
    DESTINATION: str = "Destination" 
    ETA: str = "ETA" 
    DATA_SOURCE: str = "Data source type" 
    SIZE_A: str = "A" 
    SIZE_B: str = "B" 
    SIZE_C: str = "C" 
    SIZE_D: str = "D" 

    def all(self) -> List[str]:
        return [v for k, v in self.__dict__.items()]
    
    def dtype_map(self) -> dict[str, str]:
        """Expected pandas dtypes for each CSV column."""
        return {
            self.MMSI: "Int64",
            self.IMO: "Int64",
            self.LATITUDE: "float64",
            self.LONGITUDE: "float64",
            self.ROT: "float64",
            self.SOG: "float64",
            self.COG: "float64",
            self.HEADING: "float64",
            self.WIDTH: "float64",
            self.LENGTH: "float64",
            self.DRAUGHT: "float64",
            self.SIZE_A: "Int64",
            self.SIZE_B: "Int64",
            self.SIZE_C: "Int64",
            self.SIZE_D: "Int64",
            self.TIMESTAMP: "datetime64[ns]",
            self.ETA: "datetime64[ns]",
        }
