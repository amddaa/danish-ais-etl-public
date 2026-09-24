import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import type { VesselInfo } from "../lib/types";
import type { PortDestination } from "./helpers";

export interface VesselModalState {
  mmsi: string;
  vessel: VesselInfo;
  minPct: number;
  avgPct: number;
  maxPct: number;
  minLabel: string;
  avgLabel: string;
  maxLabel: string;
}

const FOCUSABLE =
  'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

function useModalA11y(open: boolean, panelRef: RefObject<HTMLElement | null>, onClose: () => void) {
  const prevFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    prevFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const panel = panelRef.current;
    const initial =
      (panel?.querySelector(".modal-close") as HTMLElement | null) ||
      (panel?.querySelector(FOCUSABLE) as HTMLElement | null);
    initial?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panel) return;
      const nodes = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => !el.hasAttribute("disabled") && el.tabIndex !== -1,
      );
      if (!nodes.length) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      prevFocus.current?.focus();
    };
  }, [open, onClose, panelRef]);
}

export function VesselModal({ state, onClose }: { state: VesselModalState | null; onClose: () => void }) {
  const panelRef = useRef<HTMLDivElement>(null);
  useModalA11y(!!state, panelRef, onClose);
  return (
    <div
      className={"modal" + (state ? " open" : "")}
      role="dialog"
      aria-modal="true"
      aria-labelledby="vessel-modal-title"
      hidden={!state}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-content" ref={panelRef}>
        <div className="modal-header">
          <h2 id="vessel-modal-title">{state ? state.vessel.name || "Unknown vessel" : "Vessel"}</h2>
          <button type="button" className="modal-close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="modal-body">
          <div className="detail-grid">
            <div className="detail-item">
              <label>MMSI</label>
              <span>{state ? state.vessel.mmsi : "—"}</span>
            </div>
            <div className="detail-item">
              <label>Vessel ID</label>
              <span>{state ? state.vessel.vessel_id || "—" : "—"}</span>
            </div>
            <div className="detail-item">
              <label>Ship type</label>
              <span>{state ? state.vessel.ship_type || "—" : "—"}</span>
            </div>
            <div className="detail-item">
              <label>Trips</label>
              <span>{state ? state.vessel.total_trips || "—" : "—"}</span>
            </div>
          </div>

          <div className="draught-bar">
            <h4>Draught</h4>
            <div className="draught-visual">
              <div
                className="draught-marker"
                style={{ left: `${state?.minPct ?? 20}%` }}
                title="min"
              >
                <span className="draught-tick">min</span>
              </div>
              <div
                className="draught-marker"
                style={{ left: `${state?.avgPct ?? 50}%` }}
                title="avg"
              >
                <span className="draught-tick">avg</span>
              </div>
              <div
                className="draught-marker"
                style={{ left: `${state?.maxPct ?? 80}%` }}
                title="max"
              >
                <span className="draught-tick">max</span>
              </div>
            </div>
            <div className="draught-labels">
              <span>{state?.minLabel ?? "Min"}</span>
              <span>{state?.avgLabel ?? "Avg"}</span>
              <span>{state?.maxLabel ?? "Max"}</span>
            </div>
          </div>

          {state && (
            <div className="external-links">
              <a
                href={`https://www.vesselfinder.com/vessels/details/${state.mmsi}`}
                target="_blank"
                rel="noreferrer"
                className="ext-link"
              >
                VesselFinder
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export interface PortModalState {
  portId: number;
  name: string;
}

export function PortDestinationsModal({
  state,
  destinations,
  onSelectDestination,
  onClose,
}: {
  state: PortModalState | null;
  destinations: PortDestination[];
  onSelectDestination: (lat: number, lon: number, portId: number) => void;
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  useModalA11y(!!state, panelRef, onClose);

  let list;
  if (!destinations.length) {
    list = <p className="modal-empty">No outgoing routes in the current trip filters.</p>;
  } else {
    list = (
      <div className="dest-list">
        {destinations.slice(0, 10).map((d, i) => {
          const barWidth = (d.trips / destinations[0].trips) * 100;
          return (
            <button
              key={i}
              type="button"
              className="dest-row"
              onClick={() => d.coords && onSelectDestination(d.coords[0], d.coords[1], d.portId)}
            >
              <div className="dest-row-head">
                <span className="dest-name">
                  {i + 1}. {d.name}
                </span>
                <span className="dest-trips">{d.trips} trips</span>
              </div>
              <div className="dest-bar">
                <span style={{ width: `${barWidth}%` }} />
              </div>
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div
      className={"modal" + (state ? " open" : "")}
      role="dialog"
      aria-modal="true"
      aria-labelledby="port-modal-title"
      hidden={!state}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-content" ref={panelRef}>
        <div className="modal-header">
          <h2 id="port-modal-title">Destinations from {state ? state.name : "port"}</h2>
          <button type="button" className="modal-close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="modal-body">
          <p className="modal-lead">Top 10 destinations by trip count</p>
          {list}
        </div>
      </div>
    </div>
  );
}
