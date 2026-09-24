import type { ReactNode } from "react";

export function StatRow({
  children,
  columns = 4,
}: {
  children: ReactNode;
  columns?: number;
}) {
  return (
    <div
      className="stats-row"
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
    >
      {children}
    </div>
  );
}

/** Compact notation for overflowing sidebar stats (`12.4k`); full value in `title`. */
export function compactNumber(n: number): { display: string; title: string } {
  const title = n.toLocaleString("en-GB");
  if (n >= 10_000) {
    const k = n / 1000;
    const display = `${k >= 100 ? k.toFixed(0) : k.toFixed(1).replace(/\.0$/, "")}k`;
    return { display, title };
  }
  return { display: title, title };
}

export function StatCard({
  value,
  label,
  title,
}: {
  value: ReactNode;
  label: string;
  title?: string;
}) {
  return (
    <div className="stat-card" title={title}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}
