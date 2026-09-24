// Route Analysis map overlay legend. Colors match layer renderers in helpers.ts.

interface LegendProps {
  draughtMode: boolean;
  routesActive: boolean;
  portsActive: boolean;
  terminalsActive: boolean;
  geofencesActive: boolean;
  currentMmsi: string | null;
}

function Swatch({ color, className = "" }: { color?: string; className?: string }) {
  return <div className={`legend-line ${className}`.trim()} style={color ? { background: color } : undefined} />;
}

export function Legend({
  draughtMode,
  routesActive,
  portsActive,
  terminalsActive,
  geofencesActive,
  currentMmsi,
}: LegendProps) {
  const sections: React.ReactNode[] = [];
  const key: string[] = [];

  if (draughtMode) {
    if (routesActive || portsActive) {
      key.push("draught");
      sections.push(
        <div key="draught" className="legend-block">
          <h4>Max draught</h4>
          <div className="legend-gradient">
            <div className="legend-gradient-bar legend-gradient-bar--draught" />
            <div className="legend-gradient-labels">
              <span>&lt; 5 m</span>
              <span>&gt; 10 m</span>
            </div>
          </div>
        </div>,
      );
    }
  } else if (routesActive || portsActive) {
    key.push("traffic");
    sections.push(
      <div key="traffic" className="legend-block">
        <h4>Traffic</h4>
        {routesActive && (
          <>
            <div className="legend-sub">Routes</div>
            <div className="legend-gradient">
              <div className="legend-gradient-bar legend-gradient-bar--traffic" />
              <div className="legend-gradient-labels">
                <span>Few trips</span>
                <span>Many</span>
              </div>
            </div>
          </>
        )}
        {portsActive && (
          <>
            <div className="legend-sub">Ports</div>
            <div className="legend-item">
              <Swatch className="legend-line--dot" color="#3b82f6" /> 100+ visits
            </div>
            <div className="legend-item">
              <Swatch className="legend-line--dot" color="#60a5fa" /> 50–100
            </div>
            <div className="legend-item">
              <Swatch className="legend-line--dot" color="#93c5fd" /> 20–50
            </div>
            <div className="legend-item">
              <Swatch className="legend-line--dot" color="#cbd5e1" /> &lt; 20
            </div>
          </>
        )}
      </div>,
    );
  }

  if (terminalsActive || geofencesActive) {
    key.push("infrastructure");
    sections.push(
      <div key="infrastructure" className="legend-block">
        <h4>Infrastructure</h4>
        {terminalsActive && (
          <div className="legend-item">
            <Swatch className="legend-line--dot" color="#ec4899" /> Terminals
          </div>
        )}
        {geofencesActive && (
          <div className="legend-item">
            <Swatch className="legend-line--area" /> Areas
          </div>
        )}
      </div>,
    );
  }

  if (currentMmsi) {
    key.push("tracker");
    sections.push(
      <div key="tracker" className="legend-block">
        <h4>Tracker</h4>
        <div className="legend-item">
          <Swatch className="legend-line--dot" color="#22c55e" /> Port visit
        </div>
        <div className="legend-item">
          <Swatch className="legend-line--dash" /> Voyage
        </div>
        <div className="legend-item">
          <Swatch className="legend-line--dot" color="#6366f1" /> Timeline
        </div>
        <div className="legend-outage">
          <div className="legend-outage-bar" />
          <div className="legend-outage-labels">
            <span>Continuous</span>
            <span>Outage 48h+</span>
          </div>
        </div>
      </div>,
    );
  }

  return (
    <div className="legend" data-legend-key={key.join(",")}>
      {sections.length > 0 ? sections : <h4>No active layers</h4>}
    </div>
  );
}
