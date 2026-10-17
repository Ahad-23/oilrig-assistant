import React from 'react';
import { Shapes } from 'lucide-react';

interface ShapeNode {
  id?: string;
  label?: string;
  type?: 'circle' | 'rect' | 'badge' | 'card' | 'line';
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  color?: string;
  fill?: string;
  stroke?: string;
  value?: string | number;
  subtitle?: string;
  from?: string; // For connectors
  to?: string;
}

interface DynamicShapeProps {
  title?: string;
  description?: string;
  shapes?: ShapeNode[];
  nodes?: ShapeNode[];
  items?: any[];
  svg?: string;
  viewBox?: string;
}

export const DynamicShapeRenderer: React.FC<{ data: DynamicShapeProps }> = ({ data }) => {
  const raw = data as any;
  const title = data.title || raw.title || "Dynamic Visual Component";
  const description = data.description || raw.description || "";
  const nodes: ShapeNode[] = data.shapes || data.nodes || raw.elements || raw.shapes || raw.nodes || [];
  const items = data.items || raw.items || (Array.isArray(raw.data) ? raw.data : []);

  // 1. If direct raw SVG markup is provided
  if (data.svg || raw.svg) {
    const svgContent = data.svg || raw.svg;
    return (
      <div className="neo-card neo-shadow-md" style={{ margin: '14px 0', maxWidth: '640px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', borderBottom: '2px solid var(--border-color)', paddingBottom: '8px' }}>
          <Shapes size={18} />
          <h4 style={{ fontSize: '1.05rem', fontWeight: 700, textTransform: 'uppercase' }}>{title}</h4>
        </div>
        <div 
          style={{ width: '100%', overflowX: 'auto', background: 'var(--bg-muted)', padding: '12px', border: '1.5px solid var(--border-color)' }}
          dangerouslySetInnerHTML={{ __html: svgContent }} 
        />
      </div>
    );
  }

  // 2. If SVG geometric nodes are provided
  if (nodes.length > 0) {
    const width = 600;
    const height = 320;

    return (
      <div className="neo-card neo-shadow-md" style={{ margin: '14px 0', maxWidth: '640px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', borderBottom: '2px solid var(--border-color)', paddingBottom: '8px' }}>
          <Shapes size={18} />
          <h4 style={{ fontSize: '1.05rem', fontWeight: 700, textTransform: 'uppercase' }}>{title}</h4>
        </div>

        {description && (
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '10px' }}>{description}</p>
        )}

        <div style={{ border: '2px solid var(--border-color)', background: '#f8fafc', position: 'relative', overflow: 'hidden' }}>
          <svg viewBox={data.viewBox || `0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
            <defs>
              <pattern id="shape-grid" width="20" height="20" patternUnits="userSpaceOnUse">
                <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#e2e8f0" strokeWidth="1" />
              </pattern>
              <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#111827" />
              </marker>
            </defs>

            <rect width={width} height={height} fill="url(#shape-grid)" />

            {/* Render connections / lines */}
            {nodes.filter(n => n.type === 'line' || (n.from && n.to)).map((line, idx) => {
              const x1 = line.x || 40;
              const y1 = line.y || 40;
              const x2 = line.width ? x1 + line.width : 200;
              const y2 = line.height ? y1 + line.height : y1;
              return (
                <line 
                  key={`line-${idx}`} 
                  x1={x1} 
                  y1={y1} 
                  x2={x2} 
                  y2={y2} 
                  stroke={line.stroke || '#111827'} 
                  strokeWidth="2.5" 
                  markerEnd="url(#arrow)" 
                />
              );
            })}

            {/* Render shape nodes */}
            {nodes.filter(n => n.type !== 'line').map((node, idx) => {
              const x = node.x ?? (60 + (idx % 3) * 180);
              const y = node.y ?? (50 + Math.floor(idx / 3) * 110);
              const w = node.width ?? 140;
              const h = node.height ?? 65;
              const fill = node.fill || node.color || 'var(--accent-yellow-light)';
              const stroke = node.stroke || '#111827';

              if (node.type === 'circle') {
                const r = Math.min(w, h) / 2;
                return (
                  <g key={`node-${idx}`}>
                    <circle cx={x + r} cy={y + r} r={r} fill={fill} stroke={stroke} strokeWidth="2.5" />
                    {node.label && (
                      <text x={x + r} y={y + r + 4} textAnchor="middle" fontSize="11" fontWeight="700" fill="#111827">
                        {node.label}
                      </text>
                    )}
                  </g>
                );
              }

              // Default: Neobrutalist Block / Rectangle
              return (
                <g key={`node-${idx}`}>
                  {/* Drop Shadow */}
                  <rect x={x + 3} y={y + 3} width={w} height={h} fill="#111827" />
                  {/* Shape Box */}
                  <rect x={x} y={y} width={w} height={h} fill={fill} stroke={stroke} strokeWidth="2" />
                  {/* Label */}
                  {node.label && (
                    <text x={x + w / 2} y={y + (node.value ? 24 : h / 2 + 4)} textAnchor="middle" fontSize="11" fontWeight="800" fill="#111827">
                      {node.label}
                    </text>
                  )}
                  {/* Value / Subtitle */}
                  {node.value && (
                    <text x={x + w / 2} y={y + 45} textAnchor="middle" fontSize="13" fontWeight="900" fontFamily="var(--font-mono)" fill="#0f172a">
                      {node.value}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        </div>
      </div>
    );
  }

  // 3. If dynamic tile items or card grid
  if (items && items.length > 0) {
    return (
      <div className="neo-card neo-shadow-md" style={{ margin: '14px 0', maxWidth: '640px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', borderBottom: '2px solid var(--border-color)', paddingBottom: '8px' }}>
          <Shapes size={18} />
          <h4 style={{ fontSize: '1.05rem', fontWeight: 700, textTransform: 'uppercase' }}>{title}</h4>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
          {items.map((it: any, idx: number) => (
            <div 
              key={idx} 
              className="neo-card neo-shadow-sm" 
              style={{ 
                padding: '12px', 
                background: it.color || (idx % 2 === 0 ? 'var(--accent-yellow-light)' : 'var(--bg-muted)'),
                border: '2px solid var(--border-color)' 
              }}
            >
              <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                {it.label || it.title || `Item ${idx + 1}`}
              </div>
              <div style={{ fontSize: '1.25rem', fontWeight: 800, marginTop: '4px' }}>
                {it.value ?? it.text ?? "-"}
              </div>
              {it.description && (
                <div style={{ fontSize: '0.75rem', marginTop: '4px', color: 'var(--text-muted)' }}>
                  {it.description}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // 4. Fallback formatted JSON block
  return (
    <div className="neo-card neo-shadow-sm" style={{ margin: '12px 0', background: 'var(--bg-muted)' }}>
      <div className="mono" style={{ fontSize: '0.8rem', fontWeight: 700 }}>
        [Visual Component: {title}]
      </div>
      <pre className="mono" style={{ fontSize: '0.75rem', marginTop: '6px', overflowX: 'auto' }}>
        {JSON.stringify(raw, null, 2)}
      </pre>
    </div>
  );
};
