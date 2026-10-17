import { useState } from 'react';
import { Navigation, Droplets } from 'lucide-react';

interface MapPinItem {
  asset_id: string;
  well_name?: string;
  lat: number;
  lon: number;
  date?: string;
  volume_bbl?: number;
  severity?: string;
}

interface WellMapProps {
  title?: string;
  area_name?: string;
  pins?: MapPinItem[];
  wells?: MapPinItem[];
  data?: MapPinItem[];
}

export const WellMap: React.FC<{ data: WellMapProps }> = ({ data }) => {
  const raw = data as any;
  const title = data.title || raw.title || `Geospatial Well Map (${data.area_name || raw.area_name || raw.area_id || "Fleet Area"})`;
  const rawPinsList: any[] =
    (Array.isArray(data) ? data : null) ||
    data.pins ||
    data.wells ||
    data.data ||
    raw.spills ||
    raw.locations ||
    raw.markers ||
    (raw.props && (raw.props.pins || raw.props.spills || raw.props.wells || raw.props.data)) ||
    [];

  const rawPins: MapPinItem[] = rawPinsList
    .map((p: any) => ({
      asset_id: p.asset_id || p.well_id || "WELL",
      well_name: p.well_name || p.name || p.asset_id || "",
      lat: Number(p.lat ?? p.latitude ?? 32.0),
      lon: Number(p.lon ?? p.longitude ?? -102.0),
      date: p.date || p.spill_date || p.inspected_at || "",
      volume_bbl: Number(p.volume_bbl ?? p.barrels ?? p.spill_est_volume_bbl ?? 0),
      severity: p.severity || (Number(p.volume_bbl ?? p.barrels ?? 0) > 2 ? "High" : "Moderate")
    }))
    .filter(p => !isNaN(p.lat) && !isNaN(p.lon) && p.lat !== 0);

  const [selectedPin, setSelectedPin] = useState<MapPinItem | null>(rawPins[0] || null);

  if (!rawPins || rawPins.length === 0) {
    return (
      <div className="neo-card neo-shadow-sm" style={{ padding: '16px', margin: '12px 0' }}>
        <p style={{ fontStyle: 'italic', color: 'var(--text-muted)' }}>No location markers available.</p>
      </div>
    );
  }

  // Calculate bounding box for SVG projection
  const lats = rawPins.map(p => p.lat);
  const lons = rawPins.map(p => p.lon);
  const minLat = Math.min(...lats) - 0.015;
  const maxLat = Math.max(...lats) + 0.015;
  const minLon = Math.min(...lons) - 0.015;
  const maxLon = Math.max(...lons) + 0.015;

  const width = 600;
  const height = 300;
  const padding = 40;

  const projectX = (lon: number) => {
    return padding + ((lon - minLon) / Math.max(maxLon - minLon, 0.001)) * (width - 2 * padding);
  };

  const projectY = (lat: number) => {
    // Invert Y for latitude (north is up)
    return height - padding - ((lat - minLat) / Math.max(maxLat - minLat, 0.001)) * (height - 2 * padding);
  };

  return (
    <div className="neo-card neo-shadow-md" style={{ margin: '14px 0', maxWidth: '640px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '2px solid var(--border-color)', paddingBottom: '10px', marginBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Navigation size={18} />
          <h4 style={{ fontSize: '1.05rem', fontWeight: 700, textTransform: 'uppercase' }}>{title}</h4>
        </div>
        <span className="neo-badge badge-blue">
          {rawPins.length} SPILL SITES
        </span>
      </div>

      {/* Map Graphic Canvas */}
      <div style={{ border: '2px solid var(--border-color)', background: '#e2e8f0', position: 'relative', overflow: 'hidden' }}>
        <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
          {/* Topographic Background Grid */}
          <defs>
            <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
              <path d="M 30 0 L 0 0 0 30" fill="none" stroke="#cbd5e1" strokeWidth="1" />
            </pattern>
          </defs>
          <rect width={width} height={height} fill="url(#grid)" />

          {/* Area boundary representation */}
          <rect x={padding - 10} y={padding - 10} width={width - 2 * padding + 20} height={height - 2 * padding + 20} 
                fill="none" stroke="#94a3b8" strokeWidth="2" strokeDasharray="4 4" />

          {/* Pins */}
          {rawPins.map((pin, idx) => {
            const cx = projectX(pin.lon);
            const cy = projectY(pin.lat);
            const isSelected = selectedPin?.asset_id === pin.asset_id;

            return (
              <g 
                key={idx} 
                onClick={() => setSelectedPin(pin)}
                style={{ cursor: 'pointer' }}
              >
                {/* Ping wave for selection */}
                {isSelected && (
                  <circle cx={cx} cy={cy} r="18" fill="none" stroke="#ef4444" strokeWidth="2" opacity="0.6">
                    <animate attributeName="r" from="10" to="24" dur="1.5s" repeatCount="indefinite" />
                    <animate attributeName="opacity" from="0.8" to="0" dur="1.5s" repeatCount="indefinite" />
                  </circle>
                )}

                {/* Marker Body */}
                <circle 
                  cx={cx} 
                  cy={cy} 
                  r={isSelected ? "11" : "8"} 
                  fill={isSelected ? "var(--accent-red)" : "var(--accent-yellow)"} 
                  stroke="var(--border-color)" 
                  strokeWidth="2.5" 
                />

                {/* Volume badge tag */}
                <g transform={`translate(${cx + 10}, ${cy - 8})`}>
                  <rect x="0" y="0" width="55" height="18" fill="#ffffff" stroke="var(--border-color)" strokeWidth="1.5" />
                  <text x="28" y="13" textAnchor="middle" fontSize="10" fontWeight="700" fontFamily="var(--font-mono)">
                    {pin.asset_id.slice(5)}
                  </text>
                </g>
              </g>
            );
          })}
        </svg>

        {/* Legend */}
        <div style={{ position: 'absolute', bottom: '8px', left: '8px', background: 'rgba(255,255,255,0.95)', border: '1.5px solid var(--border-color)', padding: '4px 8px', fontSize: '0.7rem', fontWeight: 600 }}>
          GPS Bounds: {minLat.toFixed(2)}°N to {maxLat.toFixed(2)}°N | {Math.abs(minLon).toFixed(2)}°W
        </div>
      </div>

      {/* Selected Well Metadata Drawer */}
      {selectedPin && (
        <div style={{ marginTop: '12px', padding: '10px 14px', background: 'var(--bg-muted)', border: '2px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span className="neo-badge badge-yellow">{selectedPin.asset_id}</span>
              <span style={{ fontSize: '0.85rem', fontWeight: 700 }}>{selectedPin.well_name || `Northeast Well ${selectedPin.asset_id.slice(5)}`}</span>
            </div>
            <div className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              Coordinates: {selectedPin.lat.toFixed(5)}, {selectedPin.lon.toFixed(5)}
            </div>
          </div>

          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Date: {selectedPin.date || '24 Sep 2026'}</div>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontWeight: 700, fontSize: '0.95rem', color: '#b91c1c' }}>
              <Droplets size={14} /> {selectedPin.volume_bbl !== undefined ? `${selectedPin.volume_bbl} bbl` : 'Spill Detected'}
            </div>
          </div>
        </div>
      )}

      {/* Tabular Pin Listing */}
      <div style={{ marginTop: '14px', borderTop: '2px solid var(--border-color)', paddingTop: '10px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.825rem' }}>
          <thead>
            <tr style={{ background: '#111827', color: '#ffffff' }}>
              <th style={{ padding: '8px 10px', fontWeight: 700 }}>Well</th>
              <th style={{ padding: '8px 10px', fontWeight: 700 }}>Date</th>
              <th style={{ padding: '8px 10px', fontWeight: 700 }}>Barrels</th>
              <th style={{ padding: '8px 10px', fontWeight: 700 }}>Location (lat, lon)</th>
            </tr>
          </thead>
          <tbody>
            {rawPins.map((p, idx) => (
              <tr 
                key={idx}
                onClick={() => setSelectedPin(p)}
                style={{ 
                  cursor: 'pointer',
                  borderBottom: '1px solid var(--border-color)',
                  backgroundColor: selectedPin?.asset_id === p.asset_id ? 'var(--accent-yellow-light)' : (idx % 2 === 0 ? 'var(--bg-card)' : 'var(--bg-muted)')
                }}
              >
                <td style={{ padding: '8px 10px' }}>
                  <span className="neo-badge badge-purple mono" style={{ fontSize: '0.75rem' }}>{p.asset_id}</span>
                </td>
                <td style={{ padding: '8px 10px' }}>{p.date}</td>
                <td style={{ padding: '8px 10px', fontWeight: 700, color: '#b91c1c' }}>{p.volume_bbl} bbl</td>
                <td style={{ padding: '8px 10px' }} className="mono">{p.lat.toFixed(5)}, {p.lon.toFixed(5)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
