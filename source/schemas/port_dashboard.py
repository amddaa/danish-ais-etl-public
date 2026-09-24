from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict


class DashboardPort(BaseModel):
    id: str
    name: str
    country: Optional[str] = None
    dominant: Optional[str] = None
    visits: int
    color: str
    raw_features: Dict[str, Optional[Union[float, int]]]
    lat: float
    lon: float


class ForcedAssignment(BaseModel):
    port: str
    kmeans: int


class CorrMatrix(BaseModel):
    z: List[List[Optional[float]]]
    x: List[str]
    y: List[str]


class ProfileResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    coords: List[List[float]]
    variance: List[float]
    variance_clustering_total: float
    corr: CorrMatrix
    clusters: List[int]
    cluster_names: Dict[str, str]
    optimal_k: int
    silhouette_score: float
    davies_bouldin: Optional[float] = None
    hopkins: float
    n_pca_components: int
    dbscan_n_clusters: int
    dbscan_n_noise: int
    forced_assignments: List[ForcedAssignment]
    selection_rationale: Optional[Any] = None


class ProfileDef(BaseModel):
    label: str
    icon: str
    cols: List[str]
    desc: str


class PortDashboardOutput(BaseModel):
    """Full payload for web/src/data/port_dashboard.json."""

    ports: List[DashboardPort]
    pcaData: Dict[str, ProfileResult]
    profiles: Dict[str, ProfileDef]
    featureDocs: Dict[str, str]
