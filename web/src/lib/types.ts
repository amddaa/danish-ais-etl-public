// Types for the generated data payloads consumed by the dashboards.
// These mirror the JSON files written by the Python analysis scripts into
// src/data/ (see source/analysis/routes/visualize_routes.py,
// generate_tracker_data.py and source/analysis/ports/generate_dashboard.py).

export interface DraughtStats {
  min: number;
  avg: number;
  max: number;
}

export interface GeoPointGeometry {
  type: "Point";
  coordinates: [number, number]; // [lon, lat]
}

export interface RouteEndpoint {
  port_id: number;
  name: string;
  un_locode?: string | null;
  geometry: GeoPointGeometry;
}

export interface RouteVesselStat {
  mmsi: number;
  name: string;
  ship_type: string;
  trip_count?: number;
  total_trips?: number;
  draught_stats?: DraughtStats;
}

export interface Route {
  route_id: string;
  origin: RouteEndpoint;
  destination: RouteEndpoint;
  total_trips: number;
  draught_stats?: Partial<DraughtStats>;
  vessels?: RouteVesselStat[];
}

export interface AnalysisPort {
  port_id: number;
  name: string;
  total_visits: number;
  geometry: GeoPointGeometry;
  draught_stats: Partial<DraughtStats>;
}

export type VesselIndex = Record<string, VesselInfo>;

export interface VesselInfo {
  mmsi: number;
  name: string;
  vessel_id?: string | null;
  ship_type: string;
  total_trips: number;
  draught_stats: Partial<DraughtStats>;
}

// Full Pub-150 row; only fields referenced by the UI are typed explicitly.
export interface WpiPort {
  id: number;
  wpi_number: number;
  name: string;
  un_locode: string | null;
  country_code: string | null;
  region_name: string | null;
  world_water_body: string | null;
  harbor_size: string | null;
  harbor_type: string | null;
  shelter_afforded: string | null;
  max_vessel_draft_m: number | null;
  channel_depth_m: number | null;
  cargo_pier_depth_m: number | null;
  oil_terminal_depth_m: number | null;
  lng_terminal_depth_m: number | null;
  tidal_range_m: number | null;
  vessel_traffic_service: string | null;
  traffic_separation_scheme: string | null;
  medical_facilities: string | null;
  garbage_disposal: string | null;
  supplies_fuel_oil: string | null;
  supplies_diesel_oil: string | null;
  repairs: string | null;
  dry_dock: string | null;
  railway: string | null;
  facility_ro_ro: string | null;
  facility_container: string | null;
  facility_liquid_bulk: string | null;
  facility_solid_bulk: string | null;
  facility_breakbulk: string | null;
  facility_oil_terminal: string | null;
  facility_lng_terminal: string | null;
  terminal_count?: number;
  lat: number | null;
  lon: number | null;
  [key: string]: unknown;
}

export interface Terminal {
  id: number;
  name: string;
  lat: number | null;
  lon: number | null;
  wpi_port_id: number | null;
  wpi_port_name: string | null;
  wpi_locode: string | null;
  wpi_harbor_size: string | null;
  wpi_max_draught: number | null;
}

export interface GeofenceCollection {
  type: "FeatureCollection";
  metadata?: Record<string, unknown>;
  features: GeofenceFeature[];
}

export interface GeofenceFeature {
  type: "Feature";
  properties: {
    port_id: number;
    name: string;
    wpi_number?: number | null;
    un_locode?: string | null;
    area_sq_km?: number;
    terminal_count?: number;
    buffer_nm?: number;
    country_code?: string | null;
    [key: string]: unknown;
  };
  geometry: Record<string, unknown>;
}

export interface RouteMapStats {
  routes: number;
  ports: number;
  vessels: number;
  trips: number;
}

export interface TrackerPort {
  name: string;
  un_locode: string | null;
  lat: number;
  lon: number;
}

export interface TrackerVisit {
  port_id: number;
  arrival_time: string;
  departure_time: string | null;
  stay_duration_hours?: number | null;
  draught_m?: number | null;
  length_m?: number | null;
  width_m?: number | null;
  n_positions?: number | null;
  ship_type?: string | null;
  declared_destination?: string | null;
}

export interface TrackerVoyage {
  origin_port_id: number;
  destination_port_id: number;
  voyage_duration_hours: number;
  draught_at_origin_m: number | null;
  draught_at_dest_m: number | null;
  ship_type: string | null;
  cargo_type: string | null;
  declared_destination: string | null;
}

export interface TrackerData {
  visits: Record<string, TrackerVisit[]>;
  voyages: Record<string, TrackerVoyage[]>;
  ports: Record<string, TrackerPort>;
  sample_mmsis: string[];
}

/** [lat, lon, ISO timestamp, sog, nav status, destination, draught] */
export type TrackPoint = [number, number, string, number, string, string | null, number];

export interface DashboardPort {
  id: string;
  name: string;
  country: string;
  dominant: string;
  visits: number;
  color: string;
  raw_features: Record<string, number | null>;
  lat: number;
  lon: number;
}

export interface ProfileResult {
  coords: number[][];
  variance: number[];
  variance_clustering_total: number;
  corr: { z: (number | null)[][]; x: string[]; y: string[] };
  clusters: number[];
  cluster_names: Record<string, string>;
  optimal_k: number;
  silhouette_score: number;
  davies_bouldin: number;
  hopkins: number;
  n_pca_components: number;
  dbscan_n_clusters: number;
  dbscan_n_noise: number;
  forced_assignments: { port: string; kmeans: number }[];
}

export interface ProfileDef {
  label: string;
  icon: string;
  cols: string[];
  desc: string;
}

export interface PortDashboardData {
  ports: DashboardPort[];
  pcaData: Record<string, ProfileResult>;
  profiles: Record<string, ProfileDef>;
  featureDocs: Record<string, string>;
}
