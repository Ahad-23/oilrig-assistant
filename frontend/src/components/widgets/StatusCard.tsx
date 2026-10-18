import { Activity, User, Calendar, AlertTriangle } from 'lucide-react';

interface StatusCardProps {
  asset_id?: string;
  name?: string;
  well_type?: string;
  area?: string;
  area_name?: string;
  is_producing?: boolean;
  delta_temp_c?: number;
  ambient_temp_c?: number;
  wellhead_temp_c?: number;
  threshold_c?: number;
  last_inspected_at?: string;
  inspector?: string;
  inspector_name?: string;
  method?: string;
  recorded_status?: string;
  status_stale?: boolean;
  active_notes?: string[];
  reason?: string;
}

export const StatusCard: React.FC<{ data: StatusCardProps }> = ({ data }) => {
  const raw = data as any;
  const assetId = data.asset_id || raw.asset_id || "";
  const wellName = data.name || raw.name || (assetId ? `${assetId} Wellhead` : "Well Status");
  const wellType = data.well_type || raw.well_type || "";
  const areaName = data.area_name || data.area || raw.area_name || raw.area || "";
  const isProducing = data.is_producing ?? raw.is_producing ?? null;
  const deltaT = data.delta_temp_c ?? raw.delta_temp_c ?? null;
  const threshold = data.threshold_c ?? raw.threshold_c ?? (wellType === "T350" ? 20.0 : 15.0);
  const ambientT = data.ambient_temp_c ?? raw.ambient_temp_c ?? null;
  const wellheadT = data.wellhead_temp_c ?? raw.wellhead_temp_c ?? null;
  const inspector = data.inspector || data.inspector_name || raw.inspector_name || "";
  const recordedStatus = data.recorded_status || raw.recorded_status || "";
  const isStale = data.status_stale ?? raw.is_status_stale ?? (isProducing === false && recordedStatus === "active");
  const notes = data.active_notes || raw.active_notes || (data.reason ? [data.reason] : []);

  // If no physical telemetry fields exist (e.g. not a wellhead thermal inspection),
  // render a key-value summary card if items/data are present, or return null to avoid empty N/A cards
  if (isProducing === null && deltaT === null && wellheadT === null && ambientT === null) {
    const rawItems = raw.items || (typeof raw.data === 'object' && !Array.isArray(raw.data) 
      ? Object.entries(raw.data).map(([k, v]) => ({ label: k.replace(/_/g, ' '), value: String(v) })) 
      : []);
    if (rawItems && rawItems.length > 0) {
      return (
        <div className="neo-card neo-shadow-md" style={{ width: '100%', maxWidth: '780px', margin: '10px 0' }}>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '12px', borderBottom: '2px solid var(--border-color)', paddingBottom: '8px' }}>
            {data.name || raw.title || (assetId ? `${assetId} Summary` : "Summary")}
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
            {rawItems.map((it: any, idx: number) => (
              <div key={idx} style={{ padding: '10px 14px', background: 'var(--bg-muted)', border: '1.5px solid var(--border-color)' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  {it.label || it.name}
                </div>
                <div style={{ fontSize: '1.2rem', fontWeight: 800, marginTop: '2px' }}>
                  {it.value}
                </div>
              </div>
            ))}
          </div>
        </div>
      );
    }
    return null;
  }

  return (
    <div className="neo-card neo-shadow-md" style={{ width: '100%', maxWidth: '780px', margin: '10px 0' }}>
      {/* Top Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '2px solid var(--border-color)', paddingBottom: '12px', marginBottom: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span className="neo-badge badge-yellow">{assetId}</span>
            <span className="neo-badge badge-purple">{wellType} WELL</span>
            <span className="mono" style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{areaName}</span>
          </div>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 700 }}>{wellName}</h3>
        </div>

        {/* Producing / Idle Status Badge */}
        <div>
          {isProducing ? (
            <div className="neo-badge badge-green" style={{ padding: '6px 12px', fontSize: '0.85rem' }}>
              <Activity size={16} /> PRODUCING
            </div>
          ) : (
            <div className="neo-badge badge-red" style={{ padding: '6px 12px', fontSize: '0.85rem' }}>
              <AlertTriangle size={16} /> NOT PRODUCING (IDLE)
            </div>
          )}
        </div>
      </div>

      {/* Sensor Delta Telemetry Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginBottom: '16px' }}>
        <div style={{ border: '2px solid var(--border-color)', padding: '10px', background: 'var(--bg-muted)' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
            Wellhead Temp
          </div>
          <div style={{ fontSize: '1.35rem', fontWeight: 700, marginTop: '2px' }}>
            {wellheadT !== null ? `${wellheadT.toFixed(1)} °C` : 'N/A'}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Thermal Reading</div>
        </div>

        <div style={{ border: '2px solid var(--border-color)', padding: '10px', background: 'var(--bg-muted)' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
            Ambient Air
          </div>
          <div style={{ fontSize: '1.35rem', fontWeight: 700, marginTop: '2px' }}>
            {ambientT !== null ? `${ambientT.toFixed(1)} °C` : 'N/A'}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Surface Air</div>
        </div>

        <div style={{ 
          border: '2px solid var(--border-color)', 
          padding: '10px', 
          background: isProducing ? 'var(--accent-green-light)' : 'var(--accent-red-light)' 
        }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase' }}>
            Delta T (Diff)
          </div>
          <div style={{ fontSize: '1.35rem', fontWeight: 700, marginTop: '2px', color: isProducing ? '#065f46' : '#991b1b' }}>
            {deltaT !== null ? (deltaT > 0 ? `+${deltaT.toFixed(1)}` : deltaT.toFixed(1)) + ' °C' : 'N/A'}
          </div>
          <div style={{ fontSize: '0.7rem', fontWeight: 600 }}>
            {deltaT !== null ? (deltaT >= threshold ? `≥ ${threshold.toFixed(1)} °C Limit` : `< ${threshold.toFixed(1)} °C Limit`) : ''}
          </div>
        </div>
      </div>

      {/* Metadata & Stale Record Warning */}
      <div style={{ borderTop: '2px solid var(--border-color)', paddingTop: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            <Calendar size={14} /> Last Inspected: {data.last_inspected_at ? new Date(data.last_inspected_at).toLocaleDateString() : 'N/A'}
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            <User size={14} /> Inspector: {inspector}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem' }}>
          <span>System Recorded Status: <strong>{recordedStatus}</strong></span>
          {isStale && (
            <span className="neo-badge badge-yellow" style={{ fontSize: '0.7rem' }}>
              STALE DATA (REFRESH PENDING)
            </span>
          )}
        </div>

        {/* Operational Context Notes */}
        {notes && notes.length > 0 && (
          <div style={{ marginTop: '6px', padding: '8px 12px', background: 'var(--accent-yellow-light)', border: '1.5px solid var(--border-color)', fontSize: '0.85rem' }}>
            <div style={{ fontWeight: 700, fontSize: '0.75rem', textTransform: 'uppercase', marginBottom: '2px' }}>
              Operational Feedback & Context:
            </div>
            {notes.map((n: any, i: number) => (
              <div key={i}>{n}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
