import type { MouseEvent } from "react";
import { ChevronDown } from "lucide-react";
import type { ProfileResult } from "../lib/types";

interface Props {
  pData: ProfileResult;
  noisePct: string;
  showAnomaliesList: boolean;
  hasAnomalies: boolean;
  onToggleAnomalies: () => void;
  showTooltip: (e: MouseEvent, text: string) => void;
  moveTooltip: (e: MouseEvent) => void;
  hideTooltip: () => void;
}

const METRIC_DOCS = {
  optimalK:
    "<b>Optimal clusters (K)</b><br>Recommended cluster count from Silhouette, DBI, and Gap consensus.",
  silhouette:
    "<b>Silhouette score</b><br>Cohesion vs separation, −1 to 1. Values above 0.5 indicate strong structure.",
  dbi: "<b>Davies–Bouldin index</b><br>Within-cluster scatter over between-cluster separation. Lower is better.",
  hopkins:
    "<b>Hopkins H</b><br>Clustering tendency, 0 to 1. H &gt; 0.70 suggests non-random structure.",
  pca: "<b>PCA components</b><br>Components kept to explain at least 85% of variance.",
  dbscan:
    "<b>DBSCAN noise</b><br>Ports flagged as noise. Click to list those later assigned by k-means.",
};

function MetricRow({
  label,
  value,
  doc,
  onClick,
  chevron,
  children,
  showTooltip,
  moveTooltip,
  hideTooltip,
}: {
  label: string;
  value?: string;
  doc: string;
  onClick?: () => void;
  chevron?: React.ReactNode;
  children?: React.ReactNode;
  showTooltip: (e: MouseEvent, text: string) => void;
  moveTooltip: (e: MouseEvent) => void;
  hideTooltip: () => void;
}) {
  const className = "metric-row" + (onClick ? " metric-row--btn" : "");
  const handlers = {
    onMouseEnter: (e: MouseEvent) => showTooltip(e, doc),
    onMouseLeave: hideTooltip,
    onMouseMove: (e: MouseEvent) => moveTooltip(e),
  };
  const inner = (
    <>
      <span className="metric-row__label">
        {label}
        {chevron}
      </span>
      {value !== undefined && <span className="metric-row__value">{value}</span>}
      {children}
    </>
  );
  if (onClick) {
    return (
      <button type="button" className={className} onClick={onClick} {...handlers}>
        {inner}
      </button>
    );
  }
  return (
    <div className={className} {...handlers}>
      {inner}
    </div>
  );
}

export function ClusterMetrics({
  pData,
  noisePct,
  showAnomaliesList,
  hasAnomalies,
  onToggleAnomalies,
  showTooltip,
  moveTooltip,
  hideTooltip,
}: Props) {
  const shared = { showTooltip, moveTooltip, hideTooltip };

  return (
    <div className="metric-card">
      <MetricRow label="Optimal K" value={String(pData.optimal_k)} doc={METRIC_DOCS.optimalK} {...shared} />
      <MetricRow
        label="Silhouette"
        value={String(pData.silhouette_score)}
        doc={METRIC_DOCS.silhouette}
        {...shared}
      />
      <MetricRow
        label="Davies–Bouldin"
        value={String(pData.davies_bouldin)}
        doc={METRIC_DOCS.dbi}
        {...shared}
      />
      <MetricRow label="Hopkins H" value={String(pData.hopkins)} doc={METRIC_DOCS.hopkins} {...shared} />
      <MetricRow
        label="PCA components"
        value={String(pData.n_pca_components)}
        doc={METRIC_DOCS.pca}
        {...shared}
      />
      <MetricRow
        label="DBSCAN noise"
        doc={METRIC_DOCS.dbscan}
        onClick={onToggleAnomalies}
        chevron={
          <ChevronDown
            size={12}
            aria-hidden="true"
            className={
              "metric-row__chevron" +
              (showAnomaliesList ? " is-open" : "") +
              (hasAnomalies ? "" : " is-muted")
            }
          />
        }
        {...shared}
      >
        <span className="metric-row__badge">
          {pData.dbscan_n_noise} ({noisePct}%)
        </span>
      </MetricRow>
    </div>
  );
}
