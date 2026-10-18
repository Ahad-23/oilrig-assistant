import React, { useState } from 'react';
import { Bookmark, FileText, Check } from 'lucide-react';
import type { CitationItem } from '../types';

interface CitationsListProps {
  citations: CitationItem[] | string[];
}

export const CitationsList: React.FC<CitationsListProps> = ({ citations }) => {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  if (!citations || citations.length === 0) return null;

  const handleCopyCitation = (id: string) => {
    navigator.clipboard?.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div style={{ marginTop: '14px', paddingTop: '12px', borderTop: '2px dashed var(--border-color)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.72rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '8px' }}>
        <Bookmark size={14} />
        Verifiable Records & Citations Grounding:
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
        {citations.map((c, i) => {
          const id = typeof c === 'string' ? c : c.id;
          const ref = typeof c === 'string' ? c : c.reference || c.source_type;

          let badgeClass = 'badge-yellow';
          if (id.includes('INS')) badgeClass = 'badge-blue';
          if (id.includes('MNT')) badgeClass = 'badge-purple';
          if (id.includes('SR') || id.includes('RC') || id.includes('REG') || id.includes('SOP')) badgeClass = 'badge-red';
          if (id.includes('CTX') || id.includes('NOTE') || id.includes('CORR')) badgeClass = 'badge-green';

          const isCopied = copiedId === id;

          return (
            <button
              key={i}
              className={`neo-badge ${badgeClass} mono`}
              title={`Source: ${ref || id}. Click to copy ID.`}
              style={{ 
                cursor: 'pointer', 
                padding: '4px 10px', 
                fontSize: '0.75rem',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px'
              }}
              onClick={() => handleCopyCitation(id)}
            >
              {isCopied ? <Check size={12} color="#16a34a" /> : <FileText size={12} />}
              <span>{id}</span>
              {isCopied && <span style={{ fontSize: '0.65rem' }}>COPIED</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
};
