import { Table, AlertCircle } from 'lucide-react';

interface DataTableProps {
  title?: string;
  columns?: any[];
  rows?: any[];
  data?: any;
}

export const DataTable: React.FC<{ data: DataTableProps }> = ({ data }) => {
  const raw = data as any;
  const title = data.title || raw.title || (raw.data && raw.data.title) || "Asset Data Table";

  // 1. Extract rows from all possible schema variations
  const rawRows: any[] =
    (Array.isArray(data) ? data : null) ||
    (raw.data && typeof raw.data === 'object' && Array.isArray(raw.data.rows) ? raw.data.rows : null) ||
    data.rows ||
    raw.rows ||
    (raw.data && Array.isArray(raw.data) ? raw.data : null) ||
    (raw.props && (raw.props.rows || (raw.props.data && (Array.isArray(raw.props.data) ? raw.props.data : raw.props.data.rows)))) ||
    raw.wells ||
    raw.non_producing_wells ||
    raw.results ||
    raw.records ||
    [];

  // 2. Extract columns from all possible schema variations
  const rawColumns: any[] =
    data.columns ||
    raw.columns ||
    (raw.data && typeof raw.data === 'object' && Array.isArray(raw.data.columns) ? raw.data.columns : null) ||
    (raw.props && (raw.props.columns || (raw.props.data && raw.props.data.columns))) ||
    [];

  if (!rawRows || rawRows.length === 0) {
    return (
      <div className="neo-card neo-shadow-sm" style={{ padding: '16px', margin: '12px 0' }}>
        <p style={{ fontStyle: 'italic', color: 'var(--text-muted)' }}>No records to display.</p>
      </div>
    );
  }

  const isRowArray = Array.isArray(rawRows[0]);

  // 3. Normalize columns into a consistent { key, label } structure
  const columns: Array<{ key: string | number; label: string }> = (() => {
    if (rawColumns && rawColumns.length > 0) {
      return rawColumns.map((col: any, idx: number) => {
        if (typeof col === 'string') {
          return {
            key: isRowArray ? idx : col,
            label: col
          };
        }
        if (typeof col === 'object' && col !== null) {
          return {
            key: col.key ?? (isRowArray ? idx : (col.id || col.name || idx)),
            label: col.label ?? col.name ?? col.title ?? String(col.key ?? `Col ${idx + 1}`)
          };
        }
        return { key: idx, label: `Column ${idx + 1}` };
      });
    }

    if (rawRows.length > 0) {
      if (isRowArray) {
        return rawRows[0].map((_: any, idx: number) => ({
          key: idx,
          label: `Column ${idx + 1}`
        }));
      }
      if (typeof rawRows[0] === 'object' && rawRows[0] !== null) {
        return Object.keys(rawRows[0]).map(k => ({
          key: k,
          label: k.replace(/_/g, ' ').toUpperCase()
        }));
      }
    }

    return [];
  })();

  // 4. Robust Cell Value Extractor & Formatter
  const renderCellValue = (row: any, colKey: string | number, colIndex: number) => {
    let val: any;

    if (Array.isArray(row)) {
      val = row[colIndex];
    } else if (typeof row === 'object' && row !== null) {
      val = row[colKey];
      if (val === undefined) {
        // Fallback: search key case-insensitively or stripped of spaces/underscores
        const normalizedSearch = String(colKey).toLowerCase().replace(/[\s_-]/g, '');
        const matched = Object.keys(row).find(k => k.toLowerCase().replace(/[\s_-]/g, '') === normalizedSearch);
        if (matched) {
          val = row[matched];
        } else if (Object.values(row)[colIndex] !== undefined) {
          val = Object.values(row)[colIndex];
        }
      }
    }

    if (val === undefined || val === null || val === '') return "-";

    const strVal = String(val);

    // Negative constraint detection: "No recorded reason"
    if (strVal.toLowerCase().includes("no recorded reason") || strVal.toLowerCase().includes("not documented")) {
      return (
        <span className="neo-badge badge-yellow" style={{ fontSize: '0.75rem', fontWeight: 700 }}>
          <AlertCircle size={12} /> {strVal}
        </span>
      );
    }

    // Status badges
    if (strVal === "active (out of date)" || strVal.toLowerCase().includes("stale") || strVal.toLowerCase().includes("out of date")) {
      return (
        <span className="neo-badge badge-yellow" style={{ fontSize: '0.7rem' }}>
          ACTIVE (STALE)
        </span>
      );
    }

    if (strVal.toLowerCase() === "down" || strVal.toLowerCase() === "non-producing" || strVal.toLowerCase() === "false") {
      return (
        <span className="neo-badge badge-red" style={{ fontSize: '0.7rem' }}>
          DOWN
        </span>
      );
    }

    if (strVal.toLowerCase() === "active" || strVal.toLowerCase() === "producing" || strVal.toLowerCase() === "true") {
      return (
        <span className="neo-badge badge-green" style={{ fontSize: '0.7rem' }}>
          ACTIVE
        </span>
      );
    }

    // Asset IDs (WELL-XXXX)
    if (/WELL-\d{4}/.test(strVal)) {
      return <span className="neo-badge badge-purple mono">{strVal}</span>;
    }

    // Inspection / Maintenance / Regulatory IDs
    if (/INS-|MNT-|REG-|SR-|RC-/.test(strVal)) {
      return <span className="mono" style={{ fontWeight: 600, fontSize: '0.85rem' }}>[{strVal}]</span>;
    }

    // Numbers with temperature suffix
    if (typeof val === 'number' && String(colKey).toLowerCase().includes('temp')) {
      return `${val.toFixed(1)} °C`;
    }

    return strVal;
  };

  return (
    <div className="neo-card neo-shadow-md" style={{ margin: '14px 0', overflowX: 'auto' }}>
      {/* Table Header / Title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', borderBottom: '2px solid var(--border-color)', paddingBottom: '8px' }}>
        <Table size={18} />
        <h4 style={{ fontSize: '1.05rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          {title}
        </h4>
        <span className="mono" style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>
          {rawRows.length} entries
        </span>
      </div>

      {/* Rendered Table */}
      <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
        <thead>
          <tr style={{ background: '#111827', color: '#ffffff' }}>
            {columns.map((col, idx) => (
              <th 
                key={idx} 
                style={{ 
                  padding: '10px 14px', 
                  fontWeight: 700, 
                  fontSize: '0.75rem', 
                  letterSpacing: '0.05em',
                  color: '#ffffff',
                  borderRight: idx < columns.length - 1 ? '1px solid rgba(255,255,255,0.15)' : 'none'
                }}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rawRows.map((row, rowIdx) => (
            <tr 
              key={rowIdx} 
              style={{ 
                borderBottom: '1.5px solid var(--border-color)',
                backgroundColor: rowIdx % 2 === 0 ? 'var(--bg-card)' : 'var(--bg-muted)' 
              }}
            >
              {columns.map((col, colIdx) => (
                <td key={colIdx} style={{ padding: '10px 14px', verticalAlign: 'middle' }}>
                  {renderCellValue(row, col.key, colIdx)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
