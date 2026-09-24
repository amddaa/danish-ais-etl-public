// Leaflet popup templates. Shared card markup; unknown/empty values are omitted.

import { AlertTriangle, Flag, Navigation, PlayCircle } from "lucide";
import type {
  AnalysisPort,
  GeofenceFeature,
  Route,
  RouteVesselStat,
  Terminal,
  TrackPoint,
  TrackerPort,
  TrackerVisit,
  TrackerVoyage,
  WpiPort,
} from "../lib/types";
import { escapeAttr, iconSvg } from "../lib/icons";

export const MAP_POPUP_OPTS = {
  maxWidth: 400,
  minWidth: 300,
  className: "map-popup",
  autoPanPadding: [16, 48] as [number, number],
};

function tx(v: unknown): string {
  return String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function isKnown(v: unknown): boolean {
  if (v == null) return false;
  const s = String(v).trim();
  if (!s || s === "—" || s === "-") return false;
  const lower = s.toLowerCase();
  return lower !== "unknown" && lower !== "no-code" && lower !== "no-locode";
}

function metres(v: number | null | undefined): string | null {
  if (v == null || Number.isNaN(v)) return null;
  return `${v.toFixed(1)}\u00a0m`;
}

function cleanRegion(raw: string | null | undefined): string {
  if (!raw) return "";
  return raw.split(/\s+--\s+/)[0].replace(/\s+/g, " ").trim();
}

function cleanWater(raw: string | null | undefined): string {
  if (!raw) return "";
  return raw.split(";")[0].trim();
}

function metaBits(parts: Array<string | null | undefined>): string {
  return parts.filter(isKnown).map(tx).join(" · ");
}

function header(title: string, kicker?: string, iconHtml?: string): string {
  return `<div class="popup-header">
    <div class="popup-title">
      <div class="popup-title-main">
        ${iconHtml ? `<span class="popup-icon">${iconHtml}</span>` : ""}
        <strong>${tx(title)}</strong>
      </div>
      ${kicker && isKnown(kicker) ? `<span class="popup-kicker">${tx(kicker)}</span>` : ""}
    </div>
  </div>`;
}

function meta(text: string): string {
  return text ? `<p class="popup-meta">${text}</p>` : "";
}

function stat(value: string, label: string): string {
  return `<div class="popup-stat"><div class="value">${tx(value)}</div><div class="label">${tx(label)}</div></div>`;
}

function stats(items: Array<{ value: string; label: string }>): string {
  if (!items.length) return "";
  const cols = Math.min(3, items.length);
  return `<div class="popup-stats popup-stats--${cols}">${items.map((i) => stat(i.value, i.label)).join("")}</div>`;
}

function section(title: string, inner: string): string {
  if (!inner.trim()) return "";
  return `<section class="popup-section"><h4>${tx(title)}</h4>${inner}</section>`;
}

function kv(label: string, value: string | null | undefined): string {
  if (!isKnown(value)) return "";
  return `<div class="kv"><dt>${tx(label)}</dt><dd>${tx(value)}</dd></div>`;
}

function kvList(rows: string): string {
  return rows.trim() ? `<dl class="kv-list">${rows}</dl>` : "";
}

export interface FacilityDef {
  id: string;
  label: string;
}

export const facilityMap: FacilityDef[] = [
  { id: "facility_ro_ro", label: "RoRo" },
  { id: "facility_container", label: "Container" },
  { id: "facility_liquid_bulk", label: "Liquid bulk" },
  { id: "facility_solid_bulk", label: "Solid bulk" },
  { id: "facility_breakbulk", label: "Breakbulk" },
  { id: "facility_oil_terminal", label: "Oil terminal" },
  { id: "facility_lng_terminal", label: "LNG terminal" },
  { id: "repairs", label: "Repairs" },
  { id: "dry_dock", label: "Dry dock" },
  { id: "railway", label: "Railway" },
];

export function vesselItemHtml(v: RouteVesselStat): string {
  return `<button type="button" class="vessel-item" data-action="show-vessel" data-mmsi="${escapeAttr(v.mmsi)}">
    <span class="vessel-name">${tx(v.name || "Unknown")}</span>
    <span class="vessel-trips">${v.trip_count}</span>
  </button>`;
}

export function routePopupHtml(route: Route, vesselHtml: string): string {
  const d = route.draught_stats || {};
  const items = [
    { value: String(route.total_trips), label: "Trips" },
    ...(metres(d.avg) ? [{ value: metres(d.avg)!, label: "Avg draught" }] : []),
    ...(metres(d.max) ? [{ value: metres(d.max)!, label: "Max draught" }] : []),
  ];
  return `${header(`${route.origin.name} → ${route.destination.name}`)}
    <div class="popup-body">
      ${stats(items)}
      ${section("Top vessels", vesselHtml ? `<div class="vessel-list">${vesselHtml}</div>` : "")}
    </div>`;
}

function wpiAnalysisHtml(wpi: WpiPort, aPort: AnalysisPort): string {
  const d = aPort.draught_stats || {};
  const items = [
    { value: aPort.total_visits.toLocaleString("en-GB"), label: "Visits" },
    ...(metres(d.avg) ? [{ value: metres(d.avg)!, label: "Avg draught" }] : []),
    ...(metres(d.max) ? [{ value: metres(d.max)!, label: "Max draught" }] : []),
  ];
  return `${stats(items)}
    <button type="button" class="popup-btn" data-action="show-port-destinations" data-port-id="${wpi.id}" data-port-name="${escapeAttr(wpi.name)}">
      ${iconSvg(Navigation, 14)} Destinations
    </button>`;
}

export function wpiPortPopupHtml(wpi: WpiPort, aPort: AnalysisPort | null): string {
  const subtitle = metaBits([
    wpi.country_code,
    cleanRegion(wpi.region_name),
    cleanWater(wpi.world_water_body),
  ]);

  const harbor = kvList(
    kv("Size", wpi.harbor_size) +
      kv("Type", wpi.harbor_type) +
      kv("Shelter", wpi.shelter_afforded) +
      kv("Use", typeof wpi.harbor_use === "string" ? wpi.harbor_use : null),
  );

  const depths = kvList(
    kv("Max draft", metres(wpi.max_vessel_draft_m)) +
      kv("Channel", metres(wpi.channel_depth_m)) +
      kv("Cargo pier", metres(wpi.cargo_pier_depth_m)) +
      kv("Oil terminal", metres(wpi.oil_terminal_depth_m)) +
      kv("LNG terminal", metres(wpi.lng_terminal_depth_m)) +
      kv("Tidal range", metres(wpi.tidal_range_m)),
  );

  const chips = facilityMap
    .filter((fac) => {
      const v = String(wpi[fac.id] ?? "").trim().toLowerCase();
      return v === "yes" || v === "limited";
    })
    .map((fac) => {
      const limited = String(wpi[fac.id]).trim().toLowerCase() === "limited";
      return `<span class="popup-chip">${tx(fac.label)}${limited ? " · limited" : ""}</span>`;
    })
    .join("");

  const services = kvList(
    kv("VTS", wpi.vessel_traffic_service) +
      kv("TSS", wpi.traffic_separation_scheme) +
      kv("Medical", wpi.medical_facilities) +
      kv("Garbage", wpi.garbage_disposal) +
      kv("Fuel oil", wpi.supplies_fuel_oil) +
      kv("Diesel", wpi.supplies_diesel_oil),
  );

  const nTerm = wpi.terminal_count ?? 0;
  const footer =
    nTerm > 0
      ? `<p class="popup-footer">${nTerm} ${nTerm === 1 ? "terminal" : "terminals"}</p>`
      : "";

  return `${header(wpi.name, wpi.un_locode || undefined)}
    <div class="popup-body">
      ${meta(subtitle)}
      ${aPort ? wpiAnalysisHtml(wpi, aPort) : ""}
      ${section("Harbor", harbor)}
      ${section("Depths", depths)}
      ${section("Facilities", chips ? `<div class="popup-chips">${chips}</div>` : "")}
      ${section("Services", services)}
      ${footer}
    </div>`;
}

export function geofencePopupHtml(props: GeofenceFeature["properties"]): string {
  const subtitle = metaBits([props.country_code, props.un_locode]);
  const items = [
    ...(props.area_sq_km != null
      ? [{ value: String(props.area_sq_km), label: "km²" }]
      : []),
    { value: String(props.terminal_count || 0), label: "Quays" },
    ...(props.buffer_nm != null ? [{ value: `${props.buffer_nm}\u00a0NM`, label: "Buffer" }] : []),
  ];
  return `${header(props.name || "Operational area")}
    <div class="popup-body">
      ${meta(subtitle)}
      ${stats(items)}
    </div>`;
}

export function terminalPopupHtml(t: Terminal): string {
  const linked = t.wpi_port_id != null;
  const parent = linked
    ? kvList(
        kv("Port", t.wpi_port_name) +
          kv("LOCODE", t.wpi_locode) +
          kv("Size", t.wpi_harbor_size) +
          kv("Max draught", metres(t.wpi_max_draught)),
      ) +
      `<button type="button" class="popup-btn" data-action="show-wpi-port" data-port-id="${t.wpi_port_id}">
        ${iconSvg(Navigation, 14)} Open parent port
      </button>`
    : `<p class="popup-note">${iconSvg(AlertTriangle, 14)} Not linked to a WPI port</p>`;

  return `${header(t.name || "Terminal")}
    <div class="popup-body">
      ${section(linked ? "Parent port" : "Link", parent)}
    </div>`;
}

function trackBody(p: TrackPoint, speedLabel: string): string {
  const items = [
    { value: `${p[3]} kn`, label: speedLabel },
    ...(metres(p[6]) ? [{ value: metres(p[6])!, label: "Draught" }] : []),
  ];
  return `${stats(items)}
    ${isKnown(p[4]) ? `<p class="popup-meta">${tx(p[4])}</p>` : ""}
    ${kvList(kv("Destination", p[5]) + kv("Time", p[2]) + kv("Position", `${p[0].toFixed(4)}, ${p[1].toFixed(4)}`))}`;
}

export function positionPopupHtml(p: TrackPoint): string {
  return `${header("AIS position")}
    <div class="popup-body">${trackBody(p, "Speed")}</div>`;
}

export function startEndPopupHtml(p: TrackPoint, label: string): string {
  const icon = label === "Start" ? PlayCircle : Flag;
  return `${header(`Track ${label.toLowerCase()}`, undefined, iconSvg(icon, 14))}
    <div class="popup-body">${trackBody(p, "Speed")}</div>`;
}

export function voyagePopupHtml(
  voy: TrackerVoyage,
  origin: TrackerPort,
  dest: TrackerPort,
): string {
  const items = [{ value: `${voy.voyage_duration_hours.toFixed(1)}\u00a0h`, label: "Duration" }];
  return `${header(`${origin.name} → ${dest.name}`)}
    <div class="popup-body">
      ${stats(items)}
      ${kvList(
        kv("Origin draught", metres(voy.draught_at_origin_m)) +
          kv("Dest draught", metres(voy.draught_at_dest_m)) +
          kv("Ship type", voy.ship_type) +
          kv("Cargo", voy.cargo_type) +
          kv("Declared dest.", voy.declared_destination),
      )}
    </div>`;
}

export function visitPopupHtml(v: TrackerVisit, port: TrackerPort): string {
  const stay = v.stay_duration_hours ? `${v.stay_duration_hours.toFixed(1)}\u00a0h` : null;
  const dim =
    v.length_m != null && v.width_m != null
      ? `${v.length_m.toFixed(0)}\u00a0×\u00a0${v.width_m.toFixed(0)}\u00a0m`
      : null;
  return `${header(port.name, port.un_locode || undefined)}
    <div class="popup-body">
      ${stay ? stats([{ value: stay, label: "Stay" }]) : ""}
      ${kvList(
        kv("Draught", metres(v.draught_m)) +
          kv("Size", dim) +
          kv("AIS points", v.n_positions != null ? String(v.n_positions) : null) +
          kv("Ship type", v.ship_type) +
          kv("Declared dest.", v.declared_destination),
      )}
    </div>`;
}
