// Leaflet layer renderers — 1:1 port of the legacy routes_map.html script.

import L from "leaflet";
import "leaflet-polylinedecorator";

import type {
  AnalysisPort,
  GeofenceCollection,
  Route,
  Terminal,
  TrackPoint,
  TrackerData,
  TrackerVisit,
  TrackerVoyage,
  VesselIndex,
  WpiPort,
} from "../lib/types";
import {
  getCoords,
  getDraughtColor,
  getGapColor,
  getPortFrequencyColor,
  getRouteColor,
  getRouteWeight,
  geofenceMatchesSearch,
  routeMatchesSearch,
} from "./helpers";
import {
  geofencePopupHtml,
  MAP_POPUP_OPTS,
  positionPopupHtml,
  routePopupHtml,
  startEndPopupHtml,
  terminalPopupHtml,
  vesselItemHtml,
  visitPopupHtml,
  voyagePopupHtml,
  wpiPortPopupHtml,
} from "./popups";

// leaflet-polylinedecorator patches L at import time (no official types).
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const LAny = L as any;

export interface MapLayers {
  route: L.LayerGroup;
  port: L.LayerGroup;
  portRadius: L.LayerGroup;
  terminal: L.LayerGroup;
  geofence: L.LayerGroup;
  trackerTrack: L.FeatureGroup;
  trackerVisit: L.FeatureGroup;
  trackerVoyage: L.FeatureGroup;
  trackerActive: L.FeatureGroup;
  wpiMarkers: Map<number, L.CircleMarker>;
}

export interface RouteRenderOpts {
  routesActive: boolean;
  draughtMode: boolean;
  minTrips: number;
  maxTrips: number;
  searchText: string;
}

export function renderRoutes(
  layers: MapLayers,
  routes: Route[],
  vessels: VesselIndex,
  opts: RouteRenderOpts,
): number {
  layers.route.clearLayers();
  if (!opts.routesActive) return 0;

  const q = opts.searchText.toLowerCase();
  let visibleCount = 0;

  routes.forEach((route) => {
    if (route.total_trips < opts.minTrips) return;
    if (route.total_trips > opts.maxTrips) return;
    if (q && !routeMatchesSearch(route, vessels, q)) return;

    const start = getCoords(route.origin.geometry);
    const end = getCoords(route.destination.geometry);
    if (!start || !end) return;

    const color = opts.draughtMode
      ? getDraughtColor(route.draught_stats?.max || 0)
      : getRouteColor(route.total_trips);
    const weight = opts.draughtMode
      ? Math.min(3.5, Math.max(1, (route.draught_stats?.max || 0) / 4))
      : getRouteWeight(route.total_trips);

    const polyline = L.polyline([start, end], {
      color,
      weight,
      opacity: 0.72,
      lineCap: "round",
      lineJoin: "round",
    });

    let vesselHtml = "";
    if (route.vessels) {
      route.vessels.slice(0, 5).forEach((v) => {
        vesselHtml += vesselItemHtml(v);
      });
    }

    polyline.bindPopup(routePopupHtml(route, vesselHtml), MAP_POPUP_OPTS);
    layers.route.addLayer(polyline);

    const arrow = LAny.polylineDecorator(polyline, {
      patterns: [
        {
          offset: "100%",
          repeat: 0,
          symbol: LAny.Symbol.arrowHead({
            pixelSize: 7,
            polygon: true,
            pathOptions: {
              stroke: false,
              fillColor: color,
              fillOpacity: 0.9,
            },
          }),
        },
      ],
    });
    layers.route.addLayer(arrow);
    visibleCount++;
  });

  return visibleCount;
}

export function renderPorts(
  layers: MapLayers,
  wpiPorts: WpiPort[],
  analysisPorts: AnalysisPort[],
  draughtMode: boolean,
  searchText: string,
): void {
  layers.port.clearLayers();
  layers.portRadius.clearLayers();
  layers.wpiMarkers.clear();

  const q = searchText.toLowerCase();
  const analysisLookup: Record<string, AnalysisPort> = {};
  analysisPorts.forEach((p) => {
    analysisLookup[String(p.port_id)] = p;
  });

  wpiPorts.forEach((wpi) => {
    if (!wpi.lat || !wpi.lon) return;

    if (q) {
      const match =
        (wpi.name || "").toLowerCase().includes(q) ||
        (wpi.un_locode || "").toLowerCase().includes(q) ||
        (wpi.country_code || "").toLowerCase().includes(q);
      if (!match) return;
    }

    const aPort = analysisLookup[String(wpi.id)];
    const hasAnalysis = !!aPort;
    const stats = aPort ? aPort.draught_stats : null;

    let radius = 5;
    let fillColor = "#64748b";
    let weight = 1;
    let opacity = 0.6;

    if (hasAnalysis) {
      radius = Math.min(16, Math.max(8, Math.sqrt(aPort.total_visits || 0) + 5));
      opacity = 0.95;
      weight = 2.5;
      fillColor = draughtMode
        ? getDraughtColor(stats?.max || 0)
        : getPortFrequencyColor(aPort.total_visits || 0);
    } else {
      fillColor = "#475569";
      radius = 4.5;
      opacity = 0.7;
      weight = 1.5;
    }

    const marker = L.circleMarker([wpi.lat, wpi.lon], {
      radius,
      fillColor,
      color: "#ffffff",
      weight,
      fillOpacity: opacity,
      pane: "portPane",
    });

    marker.bindPopup(wpiPortPopupHtml(wpi, aPort ?? null), MAP_POPUP_OPTS);
    layers.wpiMarkers.set(wpi.id, marker);

    if (hasAnalysis) {
      marker.on("popupopen", () => {
        layers.portRadius.clearLayers();
        L.circle([wpi.lat as number, wpi.lon as number], {
          radius: 1000,
          color: "#f59e0b",
          fillColor: "#f59e0b",
          fillOpacity: 0.05,
          weight: 1,
          dashArray: "4, 4",
        }).addTo(layers.portRadius);
      });
      marker.on("popupclose", () => layers.portRadius.clearLayers());
    }

    layers.port.addLayer(marker);
  });
}

export function renderTerminals(layers: MapLayers, terminals: Terminal[], searchText: string): void {
  layers.terminal.clearLayers();
  const q = searchText.toLowerCase();

  terminals.forEach((t) => {
    if (!t.lat || !t.lon) return;

    if (q) {
      const match =
        (t.name || "").toLowerCase().includes(q) ||
        (t.wpi_port_name || "").toLowerCase().includes(q) ||
        (t.wpi_locode || "").toLowerCase().includes(q);
      if (!match) return;
    }

    const marker = L.circleMarker([t.lat, t.lon], {
      radius: 3.5,
      fillColor: "#ec4899",
      color: "#ffffff",
      weight: 1.5,
      fillOpacity: 0.9,
      pane: "terminalPane",
    });
    marker.bindPopup(terminalPopupHtml(t), MAP_POPUP_OPTS);
    layers.terminal.addLayer(marker);
  });
}

/** Turn on the ports layer and open the parent WPI popup for a terminal. */
export function openWpiPort(layers: MapLayers, map: L.Map, portId: number): boolean {
  const marker = layers.wpiMarkers.get(portId);
  if (!marker) return false;
  if (!map.hasLayer(layers.port)) {
    map.addLayer(layers.port);
    map.addLayer(layers.portRadius);
  }
  map.setView(marker.getLatLng(), Math.max(map.getZoom(), 11));
  marker.openPopup();
  return true;
}

export function renderGeofences(
  layers: MapLayers,
  geofences: GeofenceCollection,
  searchText: string,
): void {
  layers.geofence.clearLayers();
  if (!geofences || !geofences.features) return;

  const q = searchText.toLowerCase();
  const filteredFeatures = geofences.features.filter((f) => {
    if (!q) return true;
    return geofenceMatchesSearch(f.properties, q);
  });

  L.geoJSON(
    { type: "FeatureCollection", features: filteredFeatures } as GeoJSON.FeatureCollection,
    {
      pane: "geofencePane",
      style: {
        color: "#3b82f6",
        weight: 2,
        opacity: 0.4,
        fillColor: "#3b82f6",
        fillOpacity: 0.1,
        dashArray: "4, 4",
      },
      onEachFeature: (feature, layer) => {
        layer.bindPopup(geofencePopupHtml(feature.properties), MAP_POPUP_OPTS);
      },
    },
  ).addTo(layers.geofence);
}

export function renderFullTrack(
  layers: MapLayers,
  mmsi: string,
  trackerData: TrackerData,
  tracks: Record<string, TrackPoint[]>,
): void {
  layers.trackerTrack.clearLayers();
  layers.trackerVisit.clearLayers();
  layers.trackerVoyage.clearLayers();
  layers.trackerActive.clearLayers();

  const vesselTrack = tracks[mmsi] || [];
  const vesselVisits = trackerData.visits[mmsi] || [];
  const vesselVoyages = trackerData.voyages[mmsi] || [];

  if (vesselTrack.length > 0) {
    for (let i = 1; i < vesselTrack.length; i++) {
      const p1 = vesselTrack[i - 1];
      const p2 = vesselTrack[i];
      const t1 = new Date(p1[2]).getTime();
      const t2 = new Date(p2[2]).getTime();
      const gapHours = (t2 - t1) / 3600000;
      const color = getGapColor(gapHours);
      const opacity = 0.3 + Math.min(1, gapHours / 48) * 0.5;
      const weight = 3 + Math.min(1, gapHours / 48) * 2;

      L.polyline(
        [
          [p1[0], p1[1]],
          [p2[0], p2[1]],
        ],
        {
          color,
          weight,
          opacity,
          dashArray: "5, 5",
          interactive: false,
        },
      ).addTo(layers.trackerTrack);
    }

    vesselTrack.forEach((p) => {
      const dot = L.circleMarker([p[0], p[1]], {
        radius: 3,
        color: "#ffffff",
        weight: 1,
        fillColor: "#6366f1",
        fillOpacity: 0.5,
      });
      dot.bindPopup(positionPopupHtml(p), MAP_POPUP_OPTS);
      layers.trackerTrack.addLayer(dot);
    });

    const first = vesselTrack[0];
    const last = vesselTrack[vesselTrack.length - 1];

    L.circleMarker([first[0], first[1]], {
      radius: 10,
      color: "#22c55e",
      weight: 2,
      fillColor: "#fff",
      fillOpacity: 1,
    })
      .bindPopup(startEndPopupHtml(first, "Start"), MAP_POPUP_OPTS)
      .addTo(layers.trackerTrack);

    L.circleMarker([last[0], last[1]], {
      radius: 10,
      color: "#ef4444",
      weight: 2,
      fillColor: "#fff",
      fillOpacity: 1,
    })
      .bindPopup(startEndPopupHtml(last, "End / Current"), MAP_POPUP_OPTS)
      .addTo(layers.trackerTrack);
  }

  renderVisitsAndVoyages(layers, vesselVisits, vesselVoyages, trackerData);
}

function renderVisitsAndVoyages(
  layers: MapLayers,
  visits: TrackerVisit[],
  voyages: TrackerVoyage[],
  trackerData: TrackerData,
): void {
  voyages.forEach((voy) => {
    const origin = trackerData.ports[String(voy.origin_port_id)];
    const dest = trackerData.ports[String(voy.destination_port_id)];
    if (origin && dest) {
      const line = L.polyline(
        [
          [origin.lat, origin.lon],
          [dest.lat, dest.lon],
        ],
        { color: "#f97316", weight: 4, opacity: 0.8, dashArray: "10, 10" },
      );
      line.bindPopup(voyagePopupHtml(voy, origin, dest), MAP_POPUP_OPTS);
      layers.trackerVoyage.addLayer(line);
      LAny.polylineDecorator(line, {
        patterns: [
          {
            offset: "50%",
            repeat: 0,
            symbol: LAny.Symbol.arrowHead({
              pixelSize: 10,
              pathOptions: { color: "#f97316", fillOpacity: 1 },
            }),
          },
        ],
      }).addTo(layers.trackerVoyage);
    }
  });

  visits.forEach((v) => {
    const port = trackerData.ports[String(v.port_id)];
    if (port) {
      L.circleMarker([port.lat, port.lon], {
        radius: 12,
        color: "#fff",
        fillColor: "#22c55e",
        fillOpacity: 1,
        weight: 3,
      })
        .bindPopup(visitPopupHtml(v, port), MAP_POPUP_OPTS)
        .addTo(layers.trackerVisit);
    }
  });
}

export function updateTrackerTimeline(
  layers: MapLayers,
  map: L.Map,
  mmsi: string,
  tracks: Record<string, TrackPoint[]>,
  idx: number,
): string {
  const vesselTrack = tracks[mmsi] || [];
  if (vesselTrack.length === 0) return "";

  const p = vesselTrack[idx];
  layers.trackerActive.clearLayers();

  const visibleCoords = vesselTrack.slice(0, idx + 1).map((c) => [c[0], c[1]] as [number, number]);
  L.polyline(visibleCoords, {
    color: "#6366f1",
    weight: 6,
    opacity: 0.8,
    lineJoin: "round",
    interactive: false,
  }).addTo(layers.trackerActive);

  const shipMarker = L.circleMarker([p[0], p[1]], {
    radius: 10,
    color: "#0f172a",
    weight: 2,
    fillColor: "#6366f1",
    fillOpacity: 1,
  }).addTo(layers.trackerActive);

  shipMarker.bindPopup(positionPopupHtml(p), MAP_POPUP_OPTS);

  if (!map.getBounds().contains(shipMarker.getLatLng())) {
    map.panTo(shipMarker.getLatLng());
  }

  return p[2];
}

export function zoomToVisit(layers: MapLayers, map: L.Map, idx: number): void {
  const layer = layers.trackerVisit.getLayers()[idx] as L.CircleMarker | undefined;
  if (layer && "getLatLng" in layer) {
    map.setView(layer.getLatLng(), 12);
    layer.openPopup();
  }
}

export function clearTrackerLayers(layers: MapLayers): void {
  layers.trackerTrack.clearLayers();
  layers.trackerVisit.clearLayers();
  layers.trackerVoyage.clearLayers();
  layers.trackerActive.clearLayers();
}
