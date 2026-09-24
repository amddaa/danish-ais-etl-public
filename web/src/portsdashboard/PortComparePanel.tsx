import { useEffect, useRef } from "react";
import type { PortCompare } from "./hover";

export function PortComparePanel({
  compare,
  onClear,
}: {
  compare: PortCompare | null;
  onClear: () => void;
}) {
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!compare) return;
    cardRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [compare]);

  return (
    <div className="control-section">
      <div className="compare-head">
        <h2 className="section-title">Port vs group</h2>
        {compare && (
          <button type="button" className="compare-clear" onClick={onClear}>
            Clear
          </button>
        )}
      </div>
      {!compare && (
        <p className="compare-hint">Click a port on the chart to compare it with its group.</p>
      )}
      {compare && (
        <div className="compare-card" ref={cardRef} aria-live="polite">
          <div className="compare-card__title">{compare.name}</div>
          <div className="compare-card__meta">
            {compare.locode} · {compare.country}
            <br />
            {compare.visits} visits · {compare.dominant}
            <br />
            {compare.groupName} · n={compare.groupSize}
          </div>
          <div className="compare-card__kicker">
            {compare.profileLabel} · {compare.vsLabel}
          </div>
          <table className="compare-table">
            <thead>
              <tr>
                <th>Feature</th>
                <th>Port</th>
                <th>Group</th>
                <th>Diff</th>
              </tr>
            </thead>
            <tbody>
              {compare.rows.map((row) => (
                <tr key={row.col}>
                  <td>{row.label}</td>
                  <td>{row.port}</td>
                  <td>{row.group}</td>
                  <td className={"compare-delta compare-delta--" + row.dir}>{row.delta}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
