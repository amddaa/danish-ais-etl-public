// Route Analysis datasets. Stats stay synchronous so the sidebar can paint
// before the large JSON payloads are fetched.

import statsJson from "../data/routes_map/stats.json";
import routesUrl from "../data/routes_map/routes.json?url";
import analysisPortsUrl from "../data/routes_map/ports.json?url";
import vesselsUrl from "../data/routes_map/vessels.json?url";
import wpiPortsUrl from "../data/routes_map/wpi_ports.json?url";
import terminalsUrl from "../data/routes_map/terminals.json?url";
import geofencesUrl from "../data/routes_map/geofences.json?url";
import trackerDataUrl from "../data/tracker_data.json?url";
import trackerTracksUrl from "../data/tracker_tracks.json?url";

import type {
  AnalysisPort,
  GeofenceCollection,
  Route,
  RouteMapStats,
  Terminal,
  TrackerData,
  TrackPoint,
  VesselIndex,
  WpiPort,
} from "../lib/types";

export const stats = statsJson as RouteMapStats;

export interface RouteMapPayload {
  routes: Route[];
  analysisPorts: AnalysisPort[];
  vessels: VesselIndex;
  wpiPorts: WpiPort[];
  terminals: Terminal[];
  geofences: GeofenceCollection;
  trackerData: TrackerData;
  trackerTracks: Record<string, TrackPoint[]>;
}

function assetHref(url: string): string {
  if (typeof url !== "string" || !url) {
    throw new Error("Missing map data URL");
  }
  // Vite dev serves `?url` as an origin path (/src/data/...). fetch() can use it as-is.
  if (url.startsWith("/") && !url.startsWith("/_astro") && !url.startsWith("/./")) {
    return url;
  }
  const file = url.split("/").pop();
  if (!file) throw new Error(`Bad map data URL: ${url}`);
  // Concatenate — do not use new URL(`./${file}`, import.meta.url); Vite
  // rewrites that into a glob of source files and the lookup is undefined.
  const moduleUrl = import.meta.url;
  const dir = moduleUrl.slice(0, moduleUrl.lastIndexOf("/") + 1);
  return dir + file;
}

async function fetchJson<T>(url: string): Promise<T> {
  const href = assetHref(url);
  const res = await fetch(href);
  if (!res.ok) throw new Error(`Failed to load ${href} (${res.status})`);
  return res.json() as Promise<T>;
}

export async function loadRouteMapPayload(): Promise<RouteMapPayload> {
  const [routes, analysisPorts, vessels, wpiPorts, terminals, geofences, trackerData, trackerTracks] =
    await Promise.all([
      fetchJson<Route[]>(routesUrl),
      fetchJson<AnalysisPort[]>(analysisPortsUrl),
      fetchJson<VesselIndex>(vesselsUrl),
      fetchJson<WpiPort[]>(wpiPortsUrl),
      fetchJson<Terminal[]>(terminalsUrl),
      fetchJson<GeofenceCollection>(geofencesUrl),
      fetchJson<TrackerData>(trackerDataUrl),
      fetchJson<Record<string, TrackPoint[]>>(trackerTracksUrl),
    ]);
  return {
    routes,
    analysisPorts,
    vessels,
    wpiPorts,
    terminals,
    geofences,
    trackerData,
    trackerTracks,
  };
}
