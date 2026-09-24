// Route Analysis map application — Leaflet map, layers, filters, vessel
// tracker, modals and legend. Large JSON is fetched after first paint.

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet-polylinedecorator";
import {
  Anchor as AnchorIcon,
  Container,
  Navigation,
  Shield,
  Waves,
} from "lucide-react";
import { SearchField } from "../components/SearchField";
import { Sidebar, SidebarBody, SidebarHeader } from "../components/Sidebar";
import { SectionTitle } from "../components/SectionTitle";
import { compactNumber, StatCard, StatRow } from "../components/StatCard";
import { ButtonGrid, ToggleButton } from "../components/ToggleButton";

import { loadRouteMapPayload, stats, type RouteMapPayload } from "./data";
import { Legend } from "./Legend";
import { PortDestinationsModal, VesselModal } from "./Modals";
import type { PortModalState, VesselModalState } from "./Modals";
import { TrackerPanel } from "./TrackerPanel";
import type { TrackerVesselRow } from "./TrackerPanel";
import {
  buildPortDestinations,
  maxRouteTrips as computeMaxRouteTrips,
  resolvePortDestinations,
  routeMatchesSearch,
  terminalMatchesSearch,
  wpiPortMatchesSearch,
} from "./helpers";
import {
  clearTrackerLayers,
  openWpiPort,
  renderFullTrack,
  renderGeofences,
  renderPorts,
  renderRoutes,
  renderTerminals,
  updateTrackerTimeline,
  zoomToVisit,
  type MapLayers,
} from "./mapLayers";

export function RoutesMapApp() {
  const mapElRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layersRef = useRef<MapLayers | null>(null);
  const [mapReady, setMapReady] = useState(false);

  const [data, setData] = useState<RouteMapPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [routesActive, setRoutesActive] = useState(true);
  const [geofencesActive, setGeofencesActive] = useState(false);
  const [portsActive, setPortsActive] = useState(false);
  const [terminalsActive, setTerminalsActive] = useState(false);
  const [draughtMode, setDraughtMode] = useState(false);

  const [minTrips, setMinTrips] = useState(5);
  const [tripCeiling, setTripCeiling] = useState(100);
  const [maxTrips, setMaxTrips] = useState(100);
  const [searchText, setSearchText] = useState("");

  const [visibleRouteCount, setVisibleRouteCount] = useState(stats.routes);

  const [trackerSearch, setTrackerSearch] = useState("");
  const [selectedMmsi, setSelectedMmsi] = useState<string | null>(null);
  const [animIndex, setAnimIndex] = useState(0);
  const [currentTimestamp, setCurrentTimestamp] = useState("");

  const [vesselModal, setVesselModal] = useState<VesselModalState | null>(null);
  const [portModal, setPortModal] = useState<PortModalState | null>(null);
  const [wpiFocusId, setWpiFocusId] = useState<number | null>(null);

  const loading = !data && !loadError;
  const modalOpen = !!(vesselModal || portModal);

  const tripsStat = compactNumber(stats.trips);
  const vesselsStat = compactNumber(stats.vessels);
  const portsStat = compactNumber(stats.ports);

  useLayoutEffect(() => {
    document.getElementById("routes-fallback")?.remove();
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadRouteMapPayload()
      .then((payload) => {
        if (cancelled) return;
        const ceiling = computeMaxRouteTrips(payload.routes);
        setTripCeiling(ceiling);
        setMaxTrips(ceiling);
        setData(payload);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "Unknown error";
        setLoadError(message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const portDestinations = useMemo(() => {
    if (!data) return {};
    const filtered = data.routes.filter(
      (r) => r.total_trips >= minTrips && r.total_trips <= maxTrips,
    );
    return buildPortDestinations(filtered);
  }, [data, minTrips, maxTrips]);

  const searchQuery = searchText.trim();
  const portHits = useMemo(() => {
    if (!data || !searchQuery) return 0;
    return data.wpiPorts.filter((p) => wpiPortMatchesSearch(p, searchQuery)).length;
  }, [data, searchQuery]);
  const terminalHits = useMemo(() => {
    if (!data || !searchQuery) return 0;
    return data.terminals.filter((t) => terminalMatchesSearch(t, searchQuery)).length;
  }, [data, searchQuery]);
  const routeHits = useMemo(() => {
    if (!data || !searchQuery) return 0;
    return data.routes.filter(
      (r) =>
        r.total_trips >= minTrips &&
        r.total_trips <= maxTrips &&
        routeMatchesSearch(r, data.vessels, searchQuery),
    ).length;
  }, [data, searchQuery, minTrips, maxTrips]);

  useEffect(() => {
    if (!data || !searchQuery) return;
    if (portHits > 0) setPortsActive(true);
    if (terminalHits > 0) setTerminalsActive(true);
  }, [data, searchQuery, portHits, terminalHits]);

  const showVessel = useCallback((mmsi: string) => {
    const v = data?.vessels[mmsi];
    if (!v) return;
    const dStats = v.draught_stats || {};
    const scale = 15;
    setVesselModal({
      mmsi,
      vessel: v,
      minPct: dStats.min ? (dStats.min / scale) * 100 : 20,
      avgPct: dStats.avg ? (dStats.avg / scale) * 100 : 50,
      maxPct: dStats.max ? (dStats.max / scale) * 100 : 80,
      minLabel: dStats.min ? dStats.min.toFixed(1) + "m (min)" : "0m",
      avgLabel: dStats.avg ? dStats.avg.toFixed(1) + "m (avg)" : "Avg",
      maxLabel: dStats.max ? dStats.max.toFixed(1) + "m (max)" : "15m",
    });
  }, [data]);

  const showPortDestinations = useCallback((portId: number, portName: string) => {
    setPortModal({ portId, name: portName });
  }, []);

  const showWpiPort = useCallback((portId: number) => {
    setSearchText("");
    setPortsActive(true);
    setWpiFocusId(portId);
  }, []);

  const handlersRef = useRef({ showVessel, showPortDestinations, showWpiPort });
  handlersRef.current = { showVessel, showPortDestinations, showWpiPort };

  useEffect(() => {
    const el = mapElRef.current;
    if (!el) return;

    const map = L.map(el, { zoomControl: false }).setView([56.0, 11.0], 6);
    L.control.zoom({ position: "topright" }).addTo(map);

    map.createPane("routePane");
    map.getPane("routePane")!.style.zIndex = "400";
    map.createPane("geofencePane");
    map.getPane("geofencePane")!.style.zIndex = "410";
    map.createPane("terminalPane");
    map.getPane("terminalPane")!.style.zIndex = "450";
    map.createPane("portPane");
    map.getPane("portPane")!.style.zIndex = "500";
    map.createPane("activePortPane");
    map.getPane("activePortPane")!.style.zIndex = "510";

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      subdomains: "abc",
      maxZoom: 19,
    }).addTo(map);

    const layers: MapLayers = {
      route: L.layerGroup([], { pane: "routePane" }),
      port: L.layerGroup([], { pane: "portPane" }),
      portRadius: L.layerGroup([], { pane: "activePortPane" }),
      terminal: L.layerGroup([], { pane: "terminalPane" }),
      geofence: L.layerGroup([], { pane: "geofencePane" }),
      trackerTrack: L.featureGroup(),
      trackerVisit: L.featureGroup(),
      trackerVoyage: L.featureGroup(),
      trackerActive: L.featureGroup(),
      wpiMarkers: new Map(),
    };

    layers.route.addTo(map);
    layers.portRadius.addTo(map);
    layers.trackerTrack.addTo(map);
    layers.trackerVisit.addTo(map);
    layers.trackerVoyage.addTo(map);
    layers.trackerActive.addTo(map);

    const onPopupClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      const actionEl = target?.closest?.("[data-action]") as HTMLElement | null;
      if (!actionEl) return;
      const action = actionEl.getAttribute("data-action");
      if (action === "show-vessel") {
        const mmsi = actionEl.getAttribute("data-mmsi");
        if (mmsi) handlersRef.current.showVessel(mmsi);
      } else if (action === "show-port-destinations") {
        const portId = Number(actionEl.getAttribute("data-port-id"));
        const portName = actionEl.getAttribute("data-port-name") || "";
        handlersRef.current.showPortDestinations(portId, portName);
      } else if (action === "show-wpi-port") {
        const portId = Number(actionEl.getAttribute("data-port-id"));
        if (Number.isFinite(portId)) handlersRef.current.showWpiPort(portId);
      }
    };
    el.addEventListener("click", onPopupClick);

    mapRef.current = map;
    layersRef.current = layers;
    setMapReady(true);

    const t = window.setTimeout(() => map.invalidateSize(), 100);

    return () => {
      window.clearTimeout(t);
      el.removeEventListener("click", onPopupClick);
      map.remove();
      mapRef.current = null;
      layersRef.current = null;
      setMapReady(false);
    };
  }, []);

  useEffect(() => {
    if (!mapReady || !mapRef.current || !data) return;
    mapRef.current.invalidateSize();
  }, [mapReady, data]);

  useEffect(() => {
    if (!mapReady || !layersRef.current || !data) return;
    const count = renderRoutes(layersRef.current, data.routes, data.vessels, {
      routesActive,
      draughtMode,
      minTrips,
      maxTrips,
      searchText,
    });
    if (routesActive) setVisibleRouteCount(count);
  }, [mapReady, data, routesActive, draughtMode, minTrips, maxTrips, searchText]);

  useEffect(() => {
    if (!mapReady || !layersRef.current || !data) return;
    renderPorts(layersRef.current, data.wpiPorts, data.analysisPorts, draughtMode, searchText);
  }, [mapReady, data, draughtMode, searchText]);

  useEffect(() => {
    if (wpiFocusId == null || !mapReady || !layersRef.current || !mapRef.current) return;
    if (!portsActive) return;
    if (openWpiPort(layersRef.current, mapRef.current, wpiFocusId)) {
      setWpiFocusId(null);
    }
  }, [wpiFocusId, portsActive, searchText, mapReady, data]);

  useEffect(() => {
    if (!mapReady || !layersRef.current || !data) return;
    renderTerminals(layersRef.current, data.terminals, searchText);
  }, [mapReady, data, searchText]);

  useEffect(() => {
    if (!mapReady || !layersRef.current || !data) return;
    renderGeofences(layersRef.current, data.geofences, searchText);
  }, [mapReady, data, searchText]);

  useEffect(() => {
    const map = mapRef.current;
    const layers = layersRef.current;
    if (!map || !layers) return;
    if (routesActive) map.addLayer(layers.route);
    else map.removeLayer(layers.route);
  }, [mapReady, routesActive]);

  useEffect(() => {
    const map = mapRef.current;
    const layers = layersRef.current;
    if (!map || !layers) return;
    if (geofencesActive) map.addLayer(layers.geofence);
    else map.removeLayer(layers.geofence);
  }, [mapReady, geofencesActive]);

  useEffect(() => {
    const map = mapRef.current;
    const layers = layersRef.current;
    if (!map || !layers) return;
    if (portsActive) {
      map.addLayer(layers.port);
      map.addLayer(layers.portRadius);
    } else {
      map.removeLayer(layers.port);
      map.removeLayer(layers.portRadius);
    }
  }, [mapReady, portsActive]);

  useEffect(() => {
    const map = mapRef.current;
    const layers = layersRef.current;
    if (!map || !layers) return;
    if (terminalsActive) map.addLayer(layers.terminal);
    else map.removeLayer(layers.terminal);
  }, [mapReady, terminalsActive]);

  const trackerMmsis = useMemo(
    () => (data ? Object.keys(data.trackerTracks) : []),
    [data],
  );
  const hasTrackerData = !!data && Object.keys(data.trackerData.visits).length > 0;

  const trackerResults: TrackerVesselRow[] = useMemo(() => {
    if (!data || !hasTrackerData) return [];
    const query = trackerSearch.toLowerCase().trim();
    return trackerMmsis
      .filter((mmsi) => {
        const v = data.vessels[mmsi] || { name: "Unknown", ship_type: "" };
        return (
          mmsi.includes(query) ||
          (v.name || "").toLowerCase().includes(query) ||
          (v.ship_type || "").toLowerCase().includes(query)
        );
      })
      .map((mmsi) => {
        const v = data.vessels[mmsi] || { name: "Unknown", ship_type: "" };
        return { mmsi, name: v.name || "Unknown", shipType: v.ship_type || "Other" };
      });
  }, [data, hasTrackerData, trackerMmsis, trackerSearch]);

  useEffect(() => {
    if (trackerSearch.trim().length === 0 && selectedMmsi) {
      setSelectedMmsi(null);
    }
  }, [trackerSearch, selectedMmsi]);

  useEffect(() => {
    const layers = layersRef.current;
    if (!mapReady || !layers || !data) return;
    if (!selectedMmsi) {
      clearTrackerLayers(layers);
      setAnimIndex(0);
      setCurrentTimestamp("");
      return;
    }
    const vesselVisits = data.trackerData.visits[selectedMmsi] || [];
    const vesselTrack = data.trackerTracks[selectedMmsi] || [];
    if (vesselVisits.length === 0 && vesselTrack.length === 0) return;
    renderFullTrack(layers, selectedMmsi, data.trackerData, data.trackerTracks);
    if (vesselTrack.length > 0) {
      const map = mapRef.current;
      if (map) {
        const ts = updateTrackerTimeline(layers, map, selectedMmsi, data.trackerTracks, 0);
        setCurrentTimestamp(ts);
      }
      setAnimIndex(0);
    }
  }, [mapReady, selectedMmsi, data]);

  const onTimelineChange = useCallback(
    (idx: number) => {
      setAnimIndex(idx);
      const layers = layersRef.current;
      const map = mapRef.current;
      if (!layers || !map || !selectedMmsi || !data) return;
      const ts = updateTrackerTimeline(layers, map, selectedMmsi, data.trackerTracks, idx);
      setCurrentTimestamp(ts);
    },
    [selectedMmsi, data],
  );

  const onSelectVessel = useCallback((mmsi: string) => {
    setTrackerSearch(mmsi);
    setSelectedMmsi(mmsi);
  }, []);

  const onClearTracker = useCallback(() => {
    setTrackerSearch("");
    setSelectedMmsi(null);
  }, []);

  const onZoomToVisit = useCallback((idx: number) => {
    const layers = layersRef.current;
    const map = mapRef.current;
    if (!layers || !map) return;
    zoomToVisit(layers, map, idx);
  }, []);

  const goToDestination = useCallback((lat: number, lon: number, portId: number) => {
    setPortModal(null);
    setPortsActive(true);
    setWpiFocusId(portId);
    mapRef.current?.setView([lat, lon], 10);
  }, []);

  const selectedVisits = selectedMmsi && data ? data.trackerData.visits[selectedMmsi] || [] : [];
  const selectedVoyages = selectedMmsi && data ? data.trackerData.voyages[selectedMmsi] || [] : [];
  const selectedTrack = selectedMmsi && data ? data.trackerTracks[selectedMmsi] || [] : [];
  const selectedMeta = selectedMmsi && data ? data.vessels[selectedMmsi] : undefined;
  const hasTrackerSelection =
    !!selectedMmsi && (selectedVisits.length > 0 || selectedTrack.length > 0);

  const trackerPortNames: Record<number, { name: string; un_locode: string | null }> = {};
  if (data) {
    Object.entries(data.trackerData.ports).forEach(([id, p]) => {
      trackerPortNames[Number(id)] = { name: p.name, un_locode: p.un_locode };
    });
  }

  const portModalDests =
    portModal && data
      ? resolvePortDestinations(
          portDestinations,
          portModal.portId,
          portModal.name,
          data.analysisPorts,
        )
      : [];

  let chip: { text: string; toggle?: boolean } | null = null;
  if (!loading && !loadError) {
    if (searchQuery && routeHits === 0 && portHits === 0 && terminalHits === 0) {
      chip = { text: "No routes or ports match" };
    } else if (searchQuery && portHits > 0) {
      chip = { text: `${portHits} ports match` };
    } else if (searchQuery && terminalHits > 0) {
      chip = { text: `${terminalHits} terminals match` };
    } else if (!portsActive) {
      chip = { text: "Ports off — turn on Ports to inspect WPI cards.", toggle: true };
    }
  }

  return (
    <>
      <div className="main-container">
        <Sidebar>
          <SidebarHeader title="Route Analysis" />

          <StatRow columns={4}>
            <StatCard value={visibleRouteCount.toLocaleString("en-GB")} label="Routes" />
            <StatCard value={portsStat.display} label="Ports" title={portsStat.title} />
            <StatCard value={vesselsStat.display} label="Vessels" title={vesselsStat.title} />
            <StatCard value={tripsStat.display} label="Trips" title={tripsStat.title} />
          </StatRow>

          <SidebarBody>
            <div className="control-section" id="searchSection">
              <SectionTitle>Search</SectionTitle>
              <SearchField
                id="searchInput"
                label="Search ports, vessels, types, locodes"
                placeholder="Port, vessel, type, locode…"
                value={searchText}
                onChange={setSearchText}
              />
            </div>

            <div className="control-section" id="layerSection">
              <SectionTitle>Layers</SectionTitle>
              <ButtonGrid columns={2}>
                <ToggleButton
                  pressed={routesActive}
                  id="btnRoutes"
                  title="Ship routes"
                  onClick={() => setRoutesActive((v) => !v)}
                >
                  <Navigation aria-hidden="true" /> Routes
                </ToggleButton>
                <ToggleButton
                  pressed={geofencesActive}
                  id="btnGeofences"
                  title="Operational areas"
                  onClick={() => setGeofencesActive((v) => !v)}
                >
                  <Shield aria-hidden="true" /> Areas
                </ToggleButton>
                <ToggleButton
                  pressed={portsActive}
                  id="btnPorts"
                  title="Ports and infrastructure"
                  onClick={() => setPortsActive((v) => !v)}
                >
                  <AnchorIcon aria-hidden="true" /> Ports
                </ToggleButton>
                <ToggleButton
                  pressed={terminalsActive}
                  id="btnTerminals"
                  title="Quays and terminals"
                  onClick={() => setTerminalsActive((v) => !v)}
                >
                  <Container aria-hidden="true" /> Terminals
                </ToggleButton>
              </ButtonGrid>
            </div>

            <div className="control-section" id="filterSection" hidden={!routesActive}>
              <SectionTitle>Route filters</SectionTitle>
              <div className="control-group" data-filter="trips">
                <label htmlFor="minTrips">
                  Minimum trips <span id="minTripsVal">{minTrips}</span>
                </label>
                <input
                  type="range"
                  id="minTrips"
                  min={1}
                  max={50}
                  value={minTrips}
                  onChange={(e) => setMinTrips(parseInt(e.target.value))}
                />
                <div className="range-ends">
                  <span>1</span>
                  <span>50</span>
                </div>
              </div>
              <div className="control-group" data-filter="trips">
                <label htmlFor="maxTrips">
                  Maximum trips <span id="maxTripsVal">{maxTrips}</span>
                </label>
                <input
                  type="range"
                  id="maxTrips"
                  min={10}
                  max={tripCeiling}
                  value={maxTrips}
                  step={1}
                  onChange={(e) => setMaxTrips(parseInt(e.target.value))}
                />
                <div className="range-ends">
                  <span>10</span>
                  <span>{tripCeiling.toLocaleString("en-GB")}</span>
                </div>
              </div>
            </div>

            <div className="control-section" id="draughtToggleSection">
              <SectionTitle>Color</SectionTitle>
              <ToggleButton
                pressed={draughtMode}
                id="draughtHeatmapBtn"
                data-mode="draught"
                className="toggle-btn--block"
                onClick={() => setDraughtMode((v) => !v)}
              >
                <Waves aria-hidden="true" /> Draught
              </ToggleButton>
            </div>

            <TrackerPanel
              search={trackerSearch}
              onSearchChange={setTrackerSearch}
              results={trackerResults}
              showClearButton={trackerSearch.length > 0}
              onClear={onClearTracker}
              onSelectVessel={onSelectVessel}
              selectedMmsi={hasTrackerSelection ? selectedMmsi : null}
              summaryName={selectedMeta?.name || "Unknown"}
              summaryType={selectedMeta?.ship_type || "Unknown"}
              nVisits={selectedVisits.length}
              nVoyages={selectedVoyages.length}
              trackLength={selectedTrack.length}
              animIndex={animIndex}
              onTimelineChange={onTimelineChange}
              currentTimestamp={currentTimestamp}
              visits={selectedVisits}
              portNames={trackerPortNames}
              onZoomToVisit={onZoomToVisit}
            />
          </SidebarBody>
        </Sidebar>
        <div className="map-stage" aria-hidden={modalOpen || undefined}>
          <div id="map" ref={mapElRef} />
          {chip &&
            (chip.toggle ? (
              <button
                type="button"
                className="map-chip"
                onClick={() => setPortsActive((v) => !v)}
              >
                {chip.text}
              </button>
            ) : (
              <div className="map-chip map-chip--static" role="status">
                {chip.text}
              </div>
            ))}
          {(loading || loadError) && (
            <div className={"map-overlay" + (loadError ? " map-overlay--error" : "")} role="status">
              {loadError ? (
                <>
                  <p>Could not load map data.</p>
                  <p className="map-overlay__detail">{loadError}</p>
                </>
              ) : (
                <p>Loading map…</p>
              )}
            </div>
          )}
          <Legend
            draughtMode={draughtMode}
            routesActive={routesActive}
            portsActive={portsActive}
            terminalsActive={terminalsActive}
            geofencesActive={geofencesActive}
            currentMmsi={selectedMmsi}
          />
        </div>
      </div>

      <VesselModal state={vesselModal} onClose={() => setVesselModal(null)} />
      <PortDestinationsModal
        state={portModal}
        destinations={portModalDests}
        onSelectDestination={goToDestination}
        onClose={() => setPortModal(null)}
      />
    </>
  );
}
