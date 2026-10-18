import { Flame } from 'lucide-react';

interface SpillHeatmapProps {
  title?: string;
  rows?: any[];
  matrix?: any;
  data?: any;
}

/** Month abbreviations indexed 1-12 */
const MONTH_NAMES: Record<number, string> = {
  1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
  7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
};

const MONTH_LOWER_MAP: Record<string, number> = {
  jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
  jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12
};

export const SpillHeatmap: React.FC<{ data: SpillHeatmapProps }> = ({ data }) => {
  const raw = data as any;
  const title = data.title || raw.title || "Spills by Geographic Area & Month";

  // Extract rows from various possible payload shapes
  const rawRows: any[] =
    (Array.isArray(data) ? data : null) ||
    data.rows ||
    (raw.data && typeof raw.data === 'object' && Array.isArray(raw.data.rows) ? raw.data.rows : null) ||
    data.data ||
    raw.rows ||
    raw.matrix ||
    (raw.props && (raw.props.rows || raw.props.matrix || raw.props.data || (raw.props.data && raw.props.data.rows))) ||
    [];

  if (!rawRows || rawRows.length === 0) {
    return (
      <div className="neo-card neo-shadow-sm" style={{ padding: '16px', margin: '12px 0' }}>
        <p style={{ fontStyle: 'italic', color: 'var(--text-muted)' }}>No heatmap data available.</p>
      </div>
    );
  }

  /**
   * Normalize each row into { name, monthCounts: Map<number, number>, total }.
   * Handles:
   *   A) { area: "...", months: {1: 4, 2: 3, ...}, total: 35 }      (from aggregate_spills_matrix)
   *   B) { name: "...", jan: 4, feb: 3, ..., total: 35 }             (flat month keys)
   *   C) { area_name: "...", counts: [4, 3, ...], total: 35 }        (counts array)
   *   D) ["Area Name", 5, 3, 2, ..., 37]                             (2D matrix array)
   */
  const normalizedRows = rawRows.map((row: any) => {
    if (Array.isArray(row)) {
      const name = String(row[0] || "Unknown Area");
      const monthCounts: Record<number, number> = {};
      const hasTotal = row.length > 11;
      const monthLimit = hasTotal ? row.length - 1 : row.length;
      for (let i = 1; i < monthLimit; i++) {
        monthCounts[i] = Number(row[i]) || 0;
      }
      const total = hasTotal ? Number(row[row.length - 1]) : Object.values(monthCounts).reduce((a, b) => a + b, 0);
      return { name, monthCounts, total };
    }

    const name = row.area_name || row.area || row.name || "Unknown Area";
    const monthCounts: Record<number, number> = {};

    if (row.months && typeof row.months === 'object' && !Array.isArray(row.months)) {
      // Format A: { months: {1: 4, 2: 3, ...} }
      for (const [k, v] of Object.entries(row.months)) {
        const mNum = Number(k);
        if (mNum >= 1 && mNum <= 12) {
          monthCounts[mNum] = Number(v) || 0;
        }
      }
    } else if (Array.isArray(row.counts)) {
      // Format C: counts array [jan, feb, ...]
      row.counts.forEach((v: number, i: number) => {
        monthCounts[i + 1] = Number(v) || 0;
      });
    } else {
      // Format B: flat month keys like { jan: 4, feb: 3, ... }
      for (const [key, mNum] of Object.entries(MONTH_LOWER_MAP)) {
        if (key in row) {
          monthCounts[mNum] = Number(row[key]) || 0;
        }
      }
    }

    const total = row.total ?? Object.values(monthCounts).reduce((a: number, b: number) => a + b, 0);
    return { name, monthCounts, total: Number(total) };
  });

  // Determine which months have data across all rows
  const allMonthNums = new Set<number>();
  normalizedRows.forEach(r => {
    Object.keys(r.monthCounts).forEach(k => allMonthNums.add(Number(k)));
  });
  const monthColumns = Array.from(allMonthNums).sort((a, b) => a - b);

  // If no month columns found at all, show empty state
  if (monthColumns.length === 0) {
    return (
      <div className="neo-card neo-shadow-sm" style={{ padding: '16px', margin: '12px 0' }}>
        <p style={{ fontStyle: 'italic', color: 'var(--text-muted)' }}>No monthly spill data available.</p>
      </div>
    );
  }

  // Heatmap color scale based on spill frequency
  const getCellColor = (count: number) => {
    if (count === 0) return '#f4f4f5';
    if (count <= 2) return '#fef08a';
    if (count <= 4) return '#fdba74';
    if (count <= 6) return '#f87171';
    return '#dc2626';
  };

  const getTextColor = (count: number) => {
    return count >= 6 ? '#ffffff' : '#09090b';
  };

  // Compute column totals
  const colTotals = monthColumns.map(mNum =>
    normalizedRows.reduce((acc, r) => acc + (r.monthCounts[mNum] || 0), 0)
  );

  const grandTotal = normalizedRows.reduce((acc, r) => acc + r.total, 0);
  const maxRowTotal = Math.max(...normalizedRows.map(r => r.total));

  return (
    <div className="neo-card neo-shadow-md" style={{ margin: '12px 0', overflowX: 'auto', width: '100%', maxWidth: '860px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '2px solid var(--border-color)', paddingBottom: '10px', marginBottom: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Flame size={18} />
          <h4 style={{ fontSize: '1.05rem', fontWeight: 700, textTransform: 'uppercase' }}>{title}</h4>
        </div>
        <div style={{ display: 'flex', gap: '6px', fontSize: '0.7rem', fontWeight: 600 }}>
          <span style={{ padding: '2px 6px', background: '#f4f4f5', border: '1px solid #000' }}>0</span>
          <span style={{ padding: '2px 6px', background: '#fef08a', border: '1px solid #000' }}>1-2</span>
          <span style={{ padding: '2px 6px', background: '#fdba74', border: '1px solid #000' }}>3-4</span>
          <span style={{ padding: '2px 6px', background: '#f87171', border: '1px solid #000' }}>5-6</span>
          <span style={{ padding: '2px 6px', background: '#dc2626', color: '#fff', border: '1px solid #000' }}>7+</span>
        </div>
      </div>

      {/* Matrix Table */}
      <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'center', fontSize: '0.85rem' }}>
        <thead>
          <tr style={{ background: 'var(--border-color)', color: '#ffffff' }}>
            <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 700, fontSize: '0.75rem' }}>GEOGRAPHIC AREA</th>
            {monthColumns.map(mNum => (
              <th key={mNum} style={{ padding: '8px 4px', fontWeight: 700, fontSize: '0.75rem', width: '38px' }}>
                {MONTH_NAMES[mNum] || `M${mNum}`}
              </th>
            ))}
            <th style={{ padding: '8px 8px', fontWeight: 700, fontSize: '0.75rem', background: '#000000', width: '55px' }}>TOTAL</th>
          </tr>
        </thead>
        <tbody>
          {normalizedRows.map((row, rIdx) => {
            const isHighest = row.total === maxRowTotal && maxRowTotal > 0;

            return (
              <tr
                key={rIdx}
                style={{
                  borderBottom: '1.5px solid var(--border-color)',
                  backgroundColor: isHighest ? 'var(--accent-red-light)' : 'transparent'
                }}
              >
                <td style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 700, borderRight: '2px solid var(--border-color)' }}>
                  {row.name}
                  {isHighest && (
                    <span className="neo-badge badge-red" style={{ marginLeft: '8px', fontSize: '0.65rem' }}>
                      HIGHEST
                    </span>
                  )}
                </td>

                {monthColumns.map(mNum => {
                  const count = row.monthCounts[mNum] || 0;
                  const bg = getCellColor(count);
                  const color = getTextColor(count);

                  return (
                    <td
                      key={mNum}
                      style={{
                        padding: '6px 2px',
                        background: bg,
                        color: color,
                        fontWeight: 700,
                        borderRight: '1px solid var(--border-color)',
                        fontFamily: 'var(--font-mono)'
                      }}
                    >
                      {count}
                    </td>
                  );
                })}

                <td style={{
                  padding: '8px 6px',
                  fontWeight: 800,
                  background: isHighest ? 'var(--accent-red)' : 'var(--bg-muted)',
                  borderLeft: '2px solid var(--border-color)',
                  fontFamily: 'var(--font-mono)'
                }}>
                  {row.total}
                </td>
              </tr>
            );
          })}

          {/* Monthly Totals Row */}
          <tr style={{ background: 'var(--bg-muted)', borderTop: '2.5px solid var(--border-color)', fontWeight: 700 }}>
            <td style={{ padding: '8px 12px', textAlign: 'left', textTransform: 'uppercase', fontSize: '0.75rem' }}>Monthly Total</td>
            {colTotals.map((tot, idx) => (
              <td key={idx} style={{ padding: '8px 2px', fontFamily: 'var(--font-mono)', fontSize: '0.8rem', borderRight: '1px solid var(--border-color)' }}>
                {tot}
              </td>
            ))}
            <td style={{ padding: '8px 6px', background: 'var(--border-color)', color: '#ffffff', fontFamily: 'var(--font-mono)' }}>
              {grandTotal}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
};
