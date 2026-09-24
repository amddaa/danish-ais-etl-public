// Current-profile features for a port vs its colour-group mean.

import type { DashboardPort, ProfileDef } from "../lib/types";

export type DeltaDir = "up" | "down" | "same";

export interface CompareRow {
  col: string;
  label: string;
  port: string;
  group: string;
  delta: string;
  dir: DeltaDir;
}

export interface PortCompare {
  id: string;
  name: string;
  locode: string;
  country: string;
  visits: string;
  dominant: string;
  groupName: string;
  groupSize: number;
  profileLabel: string;
  vsLabel: string;
  rows: CompareRow[];
}

export function featureLabel(col: string): string {
  const label = col
    .replace(/^pct_/, "")
    .replace(/_m$/, "")
    .replace(/_h$/, "")
    .replace(/_int$/, "")
    .replace(/_/g, " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function mean(members: DashboardPort[], col: string): number | null {
  let sum = 0;
  let n = 0;
  for (const p of members) {
    const v = p.raw_features[col];
    if (v == null || Number.isNaN(v)) continue;
    sum += v;
    n += 1;
  }
  return n ? sum / n : null;
}

export function profileMeans(members: DashboardPort[], cols: string[]): Record<string, number | null> {
  const out: Record<string, number | null> = {};
  for (const col of cols) out[col] = mean(members, col);
  return out;
}

function formatVal(col: string, v: number | null): string {
  if (v == null) return "—";
  if (col.startsWith("pct_")) return `${v.toFixed(1)}%`;
  if (col.endsWith("_m")) return `${v.toFixed(1)} m`;
  if (col.endsWith("_h")) return `${v.toFixed(1)} h`;
  if (col.endsWith("_int")) return v.toFixed(0);
  if (Math.abs(v) >= 100) return v.toLocaleString("en-GB", { maximumFractionDigits: 0 });
  return v.toFixed(2);
}

function deltaInfo(col: string, port: number, group: number): { text: string; dir: DeltaDir } {
  const d = port - group;
  const eps = col.startsWith("pct_") ? 0.5 : Math.max(0.05 * Math.abs(group || 1), 0.05);
  if (Math.abs(d) < eps) return { text: "~", dir: "same" };
  if (col.startsWith("pct_")) {
    const mag = Math.abs(d).toFixed(1);
    if (d > 0) return { text: `+${mag} pp`, dir: "up" };
    return { text: `-${mag} pp`, dir: "down" };
  }
  const mag = formatVal(col, Math.abs(d));
  if (d > 0) return { text: `+${mag}`, dir: "up" };
  return { text: `-${mag}`, dir: "down" };
}

export function shortGroupName(name: string): string {
  return name.split("(")[0].trim() || name;
}

export function comparePort(
  p: DashboardPort,
  opts: {
    profile: ProfileDef;
    groupName: string;
    groupSize: number;
    groupMeans: Record<string, number | null>;
    vsLabel: string;
  },
): PortCompare {
  const rows: CompareRow[] = opts.profile.cols
    .map((col) => {
      const portVal = p.raw_features[col];
      const groupVal = opts.groupMeans[col] ?? null;
      const spread =
        portVal != null && groupVal != null ? Math.abs(portVal - groupVal) : -1;
      const delta =
        portVal != null && groupVal != null
          ? deltaInfo(col, portVal, groupVal)
          : { text: "", dir: "same" as DeltaDir };
      return {
        col,
        label: featureLabel(col),
        port: formatVal(col, portVal),
        group: formatVal(col, groupVal),
        delta: delta.text,
        dir: delta.dir,
        spread,
        skip: portVal == null,
      };
    })
    .filter((row) => !row.skip)
    .sort((a, b) => b.spread - a.spread)
    .map(({ col, label, port, group, delta, dir }) => ({
      col,
      label,
      port,
      group,
      delta,
      dir,
    }));

  return {
    id: p.id,
    name: p.name,
    locode: p.id,
    country: p.country,
    visits: p.visits.toLocaleString("en-GB"),
    dominant: p.dominant,
    groupName: shortGroupName(opts.groupName),
    groupSize: opts.groupSize,
    profileLabel: opts.profile.label,
    vsLabel: opts.vsLabel,
    rows,
  };
}

/** Plotly-safe hover: three lines; the sidebar table is canonical. */
export function compareHoverText(c: PortCompare): string {
  return `<b>${c.name}</b><br>${c.locode}<br>Click to compare.`;
}
