// Color/scale helpers ported verbatim from the legacy routes_map.html script.

import type {
  AnalysisPort,
  GeofenceCollection,
  Route,
  RouteEndpoint,
  Terminal,
  VesselIndex,
  WpiPort,
} from "../lib/types";

/** Traffic scale stops: low (green) → high (red). Shared by map + legend. */
export const ROUTE_TRAFFIC_STOPS: readonly [string, string, string, string] = [
  "#22c55e",
  "#eab308",
  "#f97316",
  "#ef4444",
];

const ROUTE_TRAFFIC_RGB: readonly [number, number, number][] = [
  [34, 197, 94],
  [234, 179, 8],
  [249, 115, 22],
  [239, 68, 68],
];

export const ROUTE_TRAFFIC_SCALE_MAX = 10_000;

const DRAUGHT_DEEP_M = 10;
const DRAUGHT_MID_M = 7;
const DRAUGHT_SHALLOW_M = 5;
const COLOR_NO_DATA = "#64748b";
const COLOR_DRAUGHT_DEEP = "#ef4444";
const COLOR_DRAUGHT_MID = "#f97316";
const COLOR_DRAUGHT_SHALLOW = "#eab308";
const COLOR_DRAUGHT_LOW = "#22c55e";

const PORT_VISITS_HIGH = 100;
const PORT_VISITS_MID = 50;
const PORT_VISITS_LOW = 20;
const COLOR_PORT_HIGH = "#3b82f6";
const COLOR_PORT_MID = "#60a5fa";
const COLOR_PORT_LOW = "#93c5fd";
const COLOR_PORT_MIN = "#cbd5e1";

const ROUTE_WEIGHT_MIN = 1;
const ROUTE_WEIGHT_SPAN = 2.5;

function lerpChannel(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t);
}

/**
 * Position on the 1→10k traffic scale as 0..1.
 * Log decades so mid-volume routes aren't crushed into green (linear % of 10k would).
 */
export function getRouteTrafficT(trips: number, scaleMax = ROUTE_TRAFFIC_SCALE_MAX): number {
  const max = Math.max(scaleMax, 1);
  return Math.min(1, Math.max(0, Math.log10(Math.max(trips, 1)) / Math.log10(max)));
}

/** Continuous green→red from traffic %. Outliers above `scaleMax` stay full red. */
export function getRouteColor(trips: number, scaleMax = ROUTE_TRAFFIC_SCALE_MAX): string {
  const t = getRouteTrafficT(trips, scaleMax);
  const segments = ROUTE_TRAFFIC_RGB.length - 1;
  const scaled = t * segments;
  const i = Math.min(segments - 1, Math.floor(scaled));
  const local = scaled - i;
  const [r1, g1, b1] = ROUTE_TRAFFIC_RGB[i];
  const [r2, g2, b2] = ROUTE_TRAFFIC_RGB[i + 1];
  return `rgb(${lerpChannel(r1, r2, local)}, ${lerpChannel(g1, g2, local)}, ${lerpChannel(b1, b2, local)})`;
}

export function getDraughtColor(maxDraught: number): string {
  if (maxDraught <= 0) return COLOR_NO_DATA;
  if (maxDraught > DRAUGHT_DEEP_M) return COLOR_DRAUGHT_DEEP;
  if (maxDraught > DRAUGHT_MID_M) return COLOR_DRAUGHT_MID;
  if (maxDraught > DRAUGHT_SHALLOW_M) return COLOR_DRAUGHT_SHALLOW;
  return COLOR_DRAUGHT_LOW;
}

/** Thin stroke: ~1px at few trips → ~3.5px at many (same % scale as color). */
export function getRouteWeight(trips: number, scaleMax = ROUTE_TRAFFIC_SCALE_MAX): number {
  return ROUTE_WEIGHT_MIN + getRouteTrafficT(trips, scaleMax) * ROUTE_WEIGHT_SPAN;
}

export function getCoords(geometry: { coordinates?: number[] } | null | undefined): [number, number] | null {
  if (!geometry || !geometry.coordinates) return null;
  return [geometry.coordinates[1], geometry.coordinates[0]]; // [lat, lon]
}

export function getPortFrequencyColor(visits: number): string {
  if (visits > PORT_VISITS_HIGH) return COLOR_PORT_HIGH;
  if (visits > PORT_VISITS_MID) return COLOR_PORT_MID;
  if (visits > PORT_VISITS_LOW) return COLOR_PORT_LOW;
  return COLOR_PORT_MIN;
}

/** Temporal gap gradient used by the vessel tracker track rendering. */
export function getGapColor(hours: number): string {
  const ratio = Math.min(1, hours / 48); // Full red at 48h gap
  const r = Math.round(99 + (239 - 99) * ratio);
  const g = Math.round(102 + (68 - 102) * ratio);
  const b = Math.round(241 + (68 - 241) * ratio);
  return `rgb(${r},${g},${b})`;
}

export interface PortDestination {
  name: string;
  trips: number;
  coords: [number, number] | null;
  lon: number | undefined;
  lat: number | undefined;
  portId: number;
}

/** Pre-compute top destinations per origin port (legacy `portDestinations`). */
export function buildPortDestinations(routes: Route[]): Record<string, PortDestination[]> {
  const portDestinations: Record<string, PortDestination[]> = {};

  routes.forEach((route) => {
    const originId = route.origin.port_id;
    const destCoords = getCoords(route.destination.geometry);
    const destLon = route.destination.geometry?.coordinates?.[0];
    const destLat = route.destination.geometry?.coordinates?.[1];

    if (!portDestinations[originId]) {
      portDestinations[originId] = [];
    }
    portDestinations[originId].push({
      name: route.destination.name,
      trips: route.total_trips,
      coords: destCoords,
      lon: destLon,
      lat: destLat,
      portId: route.destination.port_id,
    });
  });

  Object.keys(portDestinations).forEach((portId) => {
    portDestinations[portId].sort((a, b) => b.trips - a.trips);
  });

  return portDestinations;
}

export interface PortCoordsEntry {
  coords: [number, number] | null;
  name: string;
  lon: number | undefined;
  lat: number | undefined;
}

export function buildPortCoordsLookup(ports: AnalysisPort[]): Record<number, PortCoordsEntry> {
  const lookup: Record<number, PortCoordsEntry> = {};
  ports.forEach((p) => {
    lookup[p.port_id] = {
      coords: getCoords(p.geometry),
      name: p.name,
      lon: p.geometry?.coordinates?.[0],
      lat: p.geometry?.coordinates?.[1],
    };
  });
  return lookup;
}

/** Legacy max-trips slider bound: max route trips clamped to at least 100. */
export function maxRouteTrips(routes: Route[]): number {
  let max = 0;
  if (routes.length) {
    max = Math.max(...routes.map((r) => r.total_trips ?? 0));
  }
  return Math.max(max, 100);
}

/** Route search filter (origin/destination/vessel match), legacy logic. */
export function routeMatchesSearch(route: Route, vessels: VesselIndex, searchText: string): boolean {
  const q = searchText.toLowerCase();
  const matchOrigin =
    (route.origin.name || "").toLowerCase().includes(q) ||
    (route.origin.un_locode || "").toLowerCase().includes(q);
  const matchDest =
    (route.destination.name || "").toLowerCase().includes(q) ||
    (route.destination.un_locode || "").toLowerCase().includes(q);
  const matchVessel =
    route.vessels &&
    route.vessels.some((v) => {
      const vInfo = vessels[String(v.mmsi)] || v;
      return (
        (vInfo.name || "").toLowerCase().includes(q) ||
        String(vInfo.mmsi).includes(q) ||
        (vInfo.ship_type || "").toLowerCase().includes(q)
      );
    });
  return Boolean(matchOrigin || matchDest || matchVessel);
}

export function geofenceMatchesSearch(
  props: GeofenceCollection["features"][number]["properties"],
  searchText: string,
): boolean {
  const q = searchText.toLowerCase();
  return (
    (props.name || "").toLowerCase().includes(q) ||
    (props.un_locode || "").toLowerCase().includes(q) ||
    String(props.wpi_number || "").includes(q)
  );
}

export function endpointCoords(endpoint: RouteEndpoint): [number, number] | null {
  return getCoords(endpoint.geometry);
}

export function wpiPortMatchesSearch(wpi: WpiPort, searchText: string): boolean {
  const q = searchText.toLowerCase();
  return (
    (wpi.name || "").toLowerCase().includes(q) ||
    (wpi.un_locode || "").toLowerCase().includes(q) ||
    (wpi.country_code || "").toLowerCase().includes(q)
  );
}

export function terminalMatchesSearch(t: Terminal, searchText: string): boolean {
  const q = searchText.toLowerCase();
  return (
    (t.name || "").toLowerCase().includes(q) ||
    (t.wpi_port_name || "").toLowerCase().includes(q) ||
    (t.wpi_locode || "").toLowerCase().includes(q)
  );
}

/** Destinations are keyed by analysis origin `port_id`; WPI cards pass `wpi.id`. */
export function resolvePortDestinations(
  destinations: Record<string, PortDestination[]>,
  wpiId: number,
  portName: string,
  analysisPorts: AnalysisPort[],
): PortDestination[] {
  const byKey = (id: number): PortDestination[] =>
    destinations[id] || destinations[String(id)] || [];

  const direct = byKey(wpiId);
  if (direct.length) return direct;

  const byAnalysisId = analysisPorts.find((p) => p.port_id === wpiId);
  if (byAnalysisId) {
    const dests = byKey(byAnalysisId.port_id);
    if (dests.length) return dests;
  }

  const q = portName.trim().toLowerCase();
  if (q) {
    const byName = analysisPorts.find((p) => (p.name || "").toLowerCase() === q);
    if (byName) {
      const dests = byKey(byName.port_id);
      if (dests.length) return dests;
    }
  }
  return [];
}
