import { Search, XCircle } from "lucide-react";
import { SectionTitle } from "../components/SectionTitle";
import type { TrackerVisit } from "../lib/types";

export interface TrackerVesselRow {
  mmsi: string;
  name: string;
  shipType: string;
}

interface TrackerPanelProps {
  search: string;
  onSearchChange: (value: string) => void;
  results: TrackerVesselRow[];
  showClearButton: boolean;
  onClear: () => void;
  onSelectVessel: (mmsi: string) => void;

  selectedMmsi: string | null;
  summaryName: string;
  summaryType: string;
  nVisits: number;
  nVoyages: number;

  trackLength: number;
  animIndex: number;
  onTimelineChange: (idx: number) => void;
  currentTimestamp: string;

  visits: TrackerVisit[];
  portNames: Record<number, { name: string; un_locode: string | null }>;
  onZoomToVisit: (idx: number) => void;
}

export function TrackerPanel({
  search,
  onSearchChange,
  results,
  showClearButton,
  onClear,
  onSelectVessel,
  selectedMmsi,
  summaryName,
  summaryType,
  nVisits,
  nVoyages,
  trackLength,
  animIndex,
  onTimelineChange,
  currentTimestamp,
  visits,
  portNames,
  onZoomToVisit,
}: TrackerPanelProps) {
  return (
    <div className="control-section" id="trackerSection">
      <SectionTitle>Track vessel</SectionTitle>
      <div className="control-group">
        <label htmlFor="trackerSearch">MMSI, name or type</label>
        <div className="tracker-search">
          <div className="search-field">
            <Search size={14} aria-hidden="true" className="search-field__icon" />
            <input
              type="search"
              id="trackerSearch"
              name="trackerSearch"
              autoComplete="off"
              spellCheck={false}
              placeholder="Type to search…"
              value={search}
              onChange={(e) => onSearchChange(e.target.value)}
            />
            {showClearButton && (
              <button
                type="button"
                className="tracker-search__clear"
                title="Clear tracking"
                aria-label="Clear tracking"
                onClick={onClear}
              >
                <XCircle size={18} />
              </button>
            )}
          </div>
          {search.trim() ? (
            <div className="tracker-results">
              {results.map(({ mmsi, name, shipType }) => (
                <button
                  key={mmsi}
                  type="button"
                  className="tracker-result"
                  onClick={() => onSelectVessel(mmsi)}
                >
                  <div className="tracker-result__name">{name}</div>
                  <div className="tracker-result__meta">
                    {mmsi}
                    {shipType ? ` · ${shipType}` : ""}
                  </div>
                </button>
              ))}
              {!results.length && <div className="tracker-empty">No matching vessels</div>}
            </div>
          ) : null}
        </div>
      </div>

      {selectedMmsi && (
        <div className="tracker-summary">
          <div className="tracker-summary__name">{summaryName || "Unknown"}</div>
          <div className="tracker-summary__meta">
            {selectedMmsi}
            {summaryType ? ` · ${summaryType}` : ""}
          </div>
          <div className="popup-stats popup-stats--2" style={{ marginBottom: 0 }}>
            <div className="popup-stat">
              <div className="value">{nVisits}</div>
              <div className="label">Visits</div>
            </div>
            <div className="popup-stat">
              <div className="value">{nVoyages}</div>
              <div className="label">Voyages</div>
            </div>
          </div>

          {trackLength > 0 && (
            <div className="tracker-timeline">
              <input
                type="range"
                id="animationRange"
                min={0}
                max={Math.max(0, trackLength - 1)}
                value={animIndex}
                step={1}
                onChange={(e) => onTimelineChange(parseInt(e.target.value))}
              />
              <div className="tracker-timestamp">{currentTimestamp}</div>
            </div>
          )}

          <div className="visit-list">
            {visits.map((v, i) => {
              const port = portNames[v.port_id] || { name: "Unknown port", un_locode: null };
              const arrival = new Date(v.arrival_time).toLocaleString();
              const stay = v.departure_time
                ? Math.round(
                    (new Date(v.departure_time).getTime() - new Date(v.arrival_time).getTime()) /
                      3600000,
                  ) + " h"
                : "—";
              return (
                <button
                  key={i}
                  type="button"
                  className="visit-item"
                  onClick={() => onZoomToVisit(i)}
                >
                  <div className="visit-item__name">{port.name}</div>
                  {port.un_locode ? <div className="visit-item__code">{port.un_locode}</div> : null}
                  <div className="visit-item__meta">
                    {arrival} · Stay {stay}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
