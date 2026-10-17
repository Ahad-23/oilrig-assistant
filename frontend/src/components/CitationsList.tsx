import { Bookmark, FileText } from 'lucide-react';
import type { CitationItem } from '../types';

interface CitationsListProps {
  citations: CitationItem[] | string[];
}

export const CitationsList: React.FC<CitationsListProps> = ({ citations }) => {
  if (!citations || citations.length === 0) return null;

  return (
    <div style={{ marginTop: '12px', paddingTop: '10px', borderTop: '1.5px dashed var(--border-color)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '6px' }}>
        <Bookmark size={13} />
        Verifiable Records & Citations Grounding:
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
        {citations.map((c, i) => {
          const id = typeof c === 'string' ? c : c.id;
          const ref = typeof c === 'string' ? c : c.reference || c.source_type;

          let badgeClass = 'badge-yellow';
          if (id.includes('INS')) badgeClass = 'badge-blue';
          if (id.includes('MNT')) badgeClass = 'badge-purple';
          if (id.includes('SR') || id.includes('RC') || id.includes('REG')) badgeClass = 'badge-red';
          if (id.includes('CTX') || id.includes('NOTE')) badgeClass = 'badge-green';

          return (
            <span
              key={i}
              className={`neo-badge ${badgeClass} mono`}
              title={ref}
              style={{ cursor: 'pointer', padding: '3px 8px', fontSize: '0.75rem' }}
            >
              <FileText size={11} /> {id}
            </span>
          );
        })}
      </div>
    </div>
  );
};
