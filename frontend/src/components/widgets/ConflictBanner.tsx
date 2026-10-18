import { AlertTriangle, HelpCircle, Check } from 'lucide-react';

interface ConflictBannerProps {
  asset_id?: string;
  source_a_label?: string;
  source_a_text?: string;
  source_b_label?: string;
  source_b_text?: string;
  message?: string;
  resolution_status?: string;
}

export const ConflictBanner: React.FC<{ data: ConflictBannerProps }> = ({ data }) => {
  const raw = data as any;
  const assetId = data.asset_id || raw.asset_id || "";
  const sourceA = data.source_a_label || raw.source_a_label || "Source A (Sensor Data)";
  const textA = data.source_a_text || raw.source_a_text || "No details provided.";
  const sourceB = data.source_b_label || raw.source_b_label || "Source B (Operator Claim)";
  const textB = data.source_b_text || raw.source_b_text || "No details provided.";

  return (
    <div className="neo-card neo-shadow-md" style={{ background: '#fffbeb', borderColor: '#b45309', margin: '12px 0', width: '100%', maxWidth: '780px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', borderBottom: '2px solid #b45309', paddingBottom: '8px', marginBottom: '12px' }}>
        <AlertTriangle size={20} color="#b45309" />
        <h4 style={{ fontSize: '1rem', fontWeight: 800, textTransform: 'uppercase', color: '#92400e' }}>
          Data Contradiction Detected ({assetId})
        </h4>
        <span className="neo-badge badge-yellow" style={{ marginLeft: 'auto', fontSize: '0.7rem' }}>
          UNCONFIRMED
        </span>
      </div>

      <p style={{ fontSize: '0.85rem', marginBottom: '12px', color: '#78350f' }}>
        {data.message || "A direct conflict was detected between physical sensor telemetry and reported operator claims. Both records are surfaced without bias."}
      </p>

      {/* Two Column Split */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '12px' }}>
        {/* Source A */}
        <div style={{ border: '2px solid var(--border-color)', padding: '10px', background: '#ffffff' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '4px' }}>
            {sourceA}
          </div>
          <div style={{ fontSize: '0.8rem', lineHeight: '1.4' }}>
            {textA}
          </div>
        </div>

        {/* Source B */}
        <div style={{ border: '2px solid #b45309', padding: '10px', background: '#fef3c7' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: '#92400e', marginBottom: '4px' }}>
            {sourceB}
          </div>
          <div style={{ fontSize: '0.8rem', lineHeight: '1.4' }}>
            {textB}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', borderTop: '1.5px solid #d97706', paddingTop: '10px' }}>
        <button className="neo-btn" style={{ padding: '4px 10px', fontSize: '0.75rem' }}>
          <HelpCircle size={14} /> Request Operator Re-Check
        </button>
        <button className="neo-btn neo-btn-primary" style={{ padding: '4px 10px', fontSize: '0.75rem' }}>
          <Check size={14} /> Retain Telemetry Ground Truth
        </button>
      </div>
    </div>
  );
};
