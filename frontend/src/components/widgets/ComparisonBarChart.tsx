import { BarChart3 } from 'lucide-react';

interface BarItem {
  asset_id?: string;
  name?: string;
  label?: string;
  value?: number;
  downtime_days?: number;
  cost?: number;
  well_type?: string;
}

interface ComparisonBarChartProps {
  title?: string;
  items?: BarItem[];
  data?: BarItem[];
  unit?: string;
}

export const ComparisonBarChart: React.FC<{ data: ComparisonBarChartProps }> = ({ data }) => {
  const raw = data as any;
  const title = data.title || raw.title || "Asset Comparison";
  const rawItems: BarItem[] =
    (Array.isArray(data) ? data : null) ||
    data.items ||
    data.data ||
    raw.ranking ||
    raw.wells ||
    raw.rows ||
    (raw.props && (raw.props.items || raw.props.ranking || raw.props.data || raw.props.rows)) ||
    [];
  const unit = data.unit || raw.unit || "days";

  if (!rawItems || rawItems.length === 0) {
    return (
      <div className="neo-card neo-shadow-sm" style={{ padding: '16px', margin: '12px 0' }}>
        <p style={{ fontStyle: 'italic', color: 'var(--text-muted)' }}>No comparison data available.</p>
      </div>
    );
  }

  // Normalize items
  const items = rawItems.map((item: any) => ({
    label: item.asset_id || item.well_name || item.name || item.label || "Asset",
    wellType: item.well_type || "",
    val: Number(item.value ?? item.downtime_days ?? item.downtime ?? item.cost ?? item.total_cost ?? item.cost_total ?? item.amount ?? 0)
  }));

  const maxVal = Math.max(...items.map(i => i.val), 1);

  // Colors for ranking bars
  const barColors = [
    'var(--accent-red)',    // 1st place (highest downtime)
    'var(--accent-orange)', // 2nd place
    'var(--accent-yellow)', // 3rd place
    'var(--accent-blue)',   // 4th+
  ];

  return (
    <div className="neo-card neo-shadow-md" style={{ margin: '12px 0', width: '100%', maxWidth: '780px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', borderBottom: '2px solid var(--border-color)', paddingBottom: '10px', marginBottom: '16px' }}>
        <BarChart3 size={18} />
        <h4 style={{ fontSize: '1.05rem', fontWeight: 700, textTransform: 'uppercase' }}>
          {title}
        </h4>
      </div>

      {/* Bar List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {items.map((item, idx) => {
          const widthPct = Math.max((item.val / maxVal) * 100, 8);
          const color = barColors[idx] || barColors[barColors.length - 1];

          return (
            <div key={idx}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px', fontSize: '0.85rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="neo-badge" style={{ background: '#000', color: '#fff', fontSize: '0.7rem' }}>
                    #{idx + 1}
                  </span>
                  <span className="mono" style={{ fontWeight: 700 }}>{item.label}</span>
                  {item.wellType && (
                    <span className="neo-badge badge-purple" style={{ fontSize: '0.65rem' }}>{item.wellType}</span>
                  )}
                </div>
                <div style={{ fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                  {unit === '$' || unit === 'USD' ? `$${item.val.toLocaleString()}` : `${item.val} ${unit}`}
                </div>
              </div>

              {/* Progress Bar Container */}
              <div style={{ 
                height: '24px', 
                border: '2px solid var(--border-color)', 
                background: 'var(--bg-muted)', 
                overflow: 'hidden',
                boxShadow: '1px 1px 0px var(--border-color)'
              }}>
                <div 
                  style={{ 
                    height: '100%', 
                    width: `${widthPct}%`, 
                    background: color, 
                    borderRight: '2px solid var(--border-color)',
                    transition: 'width 0.5s ease-out'
                  }} 
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
