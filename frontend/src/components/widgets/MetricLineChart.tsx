import { useState } from 'react';
import { TrendingUp, AlertTriangle, CheckCircle } from 'lucide-react';

interface MetricPoint {
  date?: string;
  inspected_at?: string;
  wellhead_temp_c?: number;
  ambient_temp_c?: number;
  delta_temp_c?: number;
  is_producing?: boolean;
}

interface MetricLineChartProps {
  title?: string;
  asset_id?: string;
  points?: MetricPoint[];
  data?: MetricPoint[];
  threshold_c?: number;
}

export const MetricLineChart: React.FC<{ data: MetricLineChartProps }> = ({ data }) => {
  const raw = data as any;
  const points: MetricPoint[] =
    (Array.isArray(data) ? data : null) ||
    data.points ||
    data.data ||
    raw.records ||
    raw.inspections ||
    raw.readings ||
    raw.trend ||
    raw.items ||
    (raw.props && (raw.props.points || raw.props.records || raw.props.data)) ||
    [];
  const title = data.title || raw.title || (data.asset_id || raw.asset_id ? `Temperature Trend (${data.asset_id || raw.asset_id})` : "Temperature Trend");
  const threshold = data.threshold_c ?? raw.threshold_c ?? 15.0;
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  if (!points || points.length === 0) {
    return (
      <div className="neo-card neo-shadow-sm" style={{ padding: '16px', margin: '12px 0' }}>
        <p style={{ fontStyle: 'italic', color: 'var(--text-muted)' }}>No time-series data available.</p>
      </div>
    );
  }

  // Normalize points to standard fields
  const normalizedPoints: MetricPoint[] = points.map((p: any, i: number) => {
    const wh = p.wellhead_temp_c ?? p.y_wellhead ?? p.wellhead ?? p.wellhead_temp ?? 0;
    const amb = p.ambient_temp_c ?? p.y_ambient ?? p.ambient ?? p.ambient_temp ?? 0;
    const dt = p.delta_temp_c ?? p.delta ?? (wh - amb);
    const dateStr = p.date ?? p.x ?? (p.inspected_at ? String(p.inspected_at).slice(0, 10) : `W${i + 1}`);
    const isProd = p.is_producing !== undefined ? p.is_producing : (dt >= threshold);
    return {
      date: dateStr,
      inspected_at: dateStr,
      wellhead_temp_c: Number(wh),
      ambient_temp_c: Number(amb),
      delta_temp_c: Number(dt),
      is_producing: isProd
    };
  });

  // Determine bounds
  const minTemp = Math.min(...normalizedPoints.map(p => Math.min(p.wellhead_temp_c ?? 0, p.ambient_temp_c ?? 0))) - 5;
  const maxTemp = Math.max(...normalizedPoints.map(p => Math.max(p.wellhead_temp_c ?? 50, p.ambient_temp_c ?? 50))) + 5;
  const tempRange = Math.max(maxTemp - minTemp, 10);

  // SVG Chart Dimensions
  const width = 600;
  const height = 260;
  const padLeft = 45;
  const padRight = 20;
  const padTop = 30;
  const padBottom = 40;
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const getX = (idx: number) => padLeft + (idx / Math.max(normalizedPoints.length - 1, 1)) * chartW;
  const getY = (val: number) => padTop + chartH - ((val - minTemp) / tempRange) * chartH;

  // Build SVG Path Strings
  const wellheadPath = normalizedPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getY(p.wellhead_temp_c ?? 0)}`).join(' ');
  const ambientPath = normalizedPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getY(p.ambient_temp_c ?? 0)}`).join(' ');

  const activePoint = hoveredIndex !== null ? normalizedPoints[hoveredIndex] : normalizedPoints[normalizedPoints.length - 1];

  return (
    <div className="neo-card neo-shadow-md" style={{ margin: '12px 0', width: '100%', maxWidth: '820px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '2px solid var(--border-color)', paddingBottom: '10px', marginBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <TrendingUp size={18} />
          <h4 style={{ fontSize: '1.05rem', fontWeight: 700, textTransform: 'uppercase' }}>{title}</h4>
        </div>
        <div style={{ display: 'flex', gap: '12px', fontSize: '0.75rem', fontWeight: 600 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '10px', height: '10px', background: '#ef4444', border: '1px solid #000' }} /> Wellhead
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '10px', height: '10px', background: '#3b82f6', border: '1px solid #000' }} /> Ambient Air
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '10px', height: '10px', background: 'var(--accent-yellow)', border: '1px solid #000' }} /> Idle (ΔT &lt; {threshold}°C)
          </span>
        </div>
      </div>

      {/* SVG Canvas */}
      <div style={{ overflowX: 'auto' }}>
        <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => {
            const yVal = minTemp + pct * tempRange;
            const yPos = getY(yVal);
            return (
              <g key={i}>
                <line x1={padLeft} y1={yPos} x2={width - padRight} y2={yPos} stroke="#e4e4e7" strokeDasharray="3 3" />
                <text x={padLeft - 6} y={yPos + 4} textAnchor="end" fontSize="10" fill="#71717a" fontFamily="var(--font-mono)">
                  {Math.round(yVal)}°C
                </text>
              </g>
            );
          })}

          {/* Axes */}
          <line x1={padLeft} y1={padTop} x2={padLeft} y2={height - padBottom} stroke="var(--border-color)" strokeWidth="2" />
          <line x1={padLeft} y1={height - padBottom} x2={width - padRight} y2={height - padBottom} stroke="var(--border-color)" strokeWidth="2" />

          {/* Ambient Air Line */}
          <path d={ambientPath} fill="none" stroke="#3b82f6" strokeWidth="2.5" />

          {/* Wellhead Temp Line */}
          <path d={wellheadPath} fill="none" stroke="#ef4444" strokeWidth="2.5" />

          {/* Points */}
          {normalizedPoints.map((p, i) => {
            const x = getX(i);
            const yWh = getY(p.wellhead_temp_c ?? 0);
            const isNonProd = p.is_producing === false || (p.delta_temp_c !== undefined && p.delta_temp_c < threshold);

            return (
              <g key={i} onMouseEnter={() => setHoveredIndex(i)} style={{ cursor: 'pointer' }}>
                {/* Ambient node */}
                <circle cx={x} cy={getY(p.ambient_temp_c ?? 0)} r="4" fill="#3b82f6" stroke="var(--border-color)" strokeWidth="1.5" />

                {/* Wellhead node */}
                <circle 
                  cx={x} 
                  cy={yWh} 
                  r={isNonProd ? "7" : "5"} 
                  fill={isNonProd ? "var(--accent-yellow)" : "#ef4444"} 
                  stroke="var(--border-color)" 
                  strokeWidth="2" 
                />

                {/* Non-producing visual flag marker */}
                {isNonProd && (
                  <g>
                    <rect x={x - 12} y={yWh - 24} width="24" height="15" fill="#fee2e2" stroke="#dc2626" strokeWidth="1.5" />
                    <text x={x} y={yWh - 13} fontSize="9" fontWeight="700" textAnchor="middle" fill="#dc2626">IDLE</text>
                  </g>
                )}

                {/* Date labels on bottom axis */}
                {(i === 0 || i === Math.floor(points.length / 2) || i === points.length - 1) && (
                  <text x={x} y={height - padBottom + 16} textAnchor="middle" fontSize="10" fill="#52525b" fontFamily="var(--font-mono)">
                    {p.date ? p.date.slice(5) : p.inspected_at ? p.inspected_at.slice(5, 10) : `W${i + 1}`}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {/* Active Point Hover Details Bar */}
      {activePoint && (
        <div style={{ marginTop: '10px', padding: '8px 12px', background: 'var(--bg-muted)', border: '1.5px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.85rem' }}>
          <div>
            <strong>Date:</strong> <span className="mono">{activePoint.date || activePoint.inspected_at?.slice(0, 10)}</span>
          </div>
          <div>
            Wellhead: <strong>{activePoint.wellhead_temp_c?.toFixed(1)}°C</strong> | Air: <strong>{activePoint.ambient_temp_c?.toFixed(1)}°C</strong>
          </div>
          <div>
            ΔT: <strong style={{ color: (activePoint.delta_temp_c ?? 0) >= threshold ? '#059669' : '#dc2626' }}>
              {(activePoint.delta_temp_c ?? 0) > 0 ? `+${activePoint.delta_temp_c?.toFixed(1)}` : activePoint.delta_temp_c?.toFixed(1)}°C
            </strong>
          </div>
          <div>
            {activePoint.is_producing === false ? (
              <span className="neo-badge badge-red"><AlertTriangle size={12} /> IDLE</span>
            ) : (
              <span className="neo-badge badge-green"><CheckCircle size={12} /> PRODUCING</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
