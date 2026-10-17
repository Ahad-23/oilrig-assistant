import { useState } from 'react';
import { Send, Zap, Radio } from 'lucide-react';

interface ChatInputProps {
  onSendMessage: (message: string, useStreaming: boolean) => void;
  disabled: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSendMessage, disabled }) => {
  const [input, setInput] = useState('');
  const [useStreaming, setUseStreaming] = useState(true);

  const quickPrompts = [
    { label: "Q1. Status Card", prompt: "Is WELL-0001 producing oil right now? When was it last inspected, and by whom? Show me its status card." },
    { label: "Q2. Area Wells Table", prompt: "Which wells in Northeast Block 8 are not producing oil right now, and why? Show them in a table." },
    { label: "Q3. Temp Trend Line", prompt: "Show a line chart of WELL-0001's wellhead temperature against air temperature for the last 13 weeks, and mark when it was not producing oil." },
    { label: "Q4. Spills Table", prompt: "How many oil spills has WELL-0001 had in the last 4 years, and how much oil in total? List them in a table." },
    { label: "Q6. Downtime Bar Chart", prompt: "Which 3 wells in Northeast Block 7 had the most downtime in the last 4 months? Show a bar chart." },
    { label: "Q7. Spill Map", prompt: "Show on a map every well in Northeast Block 8 with a real spill in the last 90 days." },
    { label: "Q8. Spills Heatmap", prompt: "Show a heatmap of 2026 spills by geographic area and month." },
    { label: "Q9. Compliance Breaches", prompt: "Which rules has WELL-0001 broken in the last 12 months, and what is still open?" },
    { label: "Q10. Containment Breaches", prompt: "In Southwest Block 24, which spills in the last 90 days were not contained within the SOP time limit?" },
    { label: "Q11. Private Follow-up", prompt: "For the three wells we discussed yesterday, what have repairs cost this year?" },
  ];

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || disabled) return;
    onSendMessage(input.trim(), useStreaming);
    setInput('');
  };

  return (
    <div style={{ marginTop: 'auto', paddingTop: '16px' }}>
      {/* Quick Benchmark Prompt Pills */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflowX: 'auto', paddingBottom: '10px', marginBottom: '8px' }}>
        <span style={{ fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
          <Zap size={13} /> Quick Scenarios:
        </span>
        {quickPrompts.map((qp, idx) => (
          <button
            key={idx}
            className="neo-btn"
            style={{ padding: '4px 8px', fontSize: '0.75rem', whiteSpace: 'nowrap', flexShrink: 0, background: '#ffffff' }}
            onClick={() => onSendMessage(qp.prompt, useStreaming)}
            disabled={disabled}
          >
            {qp.label}
          </button>
        ))}
      </div>

      {/* Input Form */}
      <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
        <div style={{ flex: 1, position: 'relative' }}>
          <input
            type="text"
            className="neo-border-thick"
            style={{
              width: '100%',
              padding: '14px 16px',
              fontFamily: 'var(--font-sans)',
              fontSize: '1rem',
              fontWeight: 500,
              background: '#ffffff',
              boxShadow: 'var(--shadow-md)',
              outline: 'none',
            }}
            placeholder="Ask about wells, downtime, temperature trends, spills, SOP breaches, or input operational corrections..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={disabled}
          />
        </div>

        {/* Streaming Mode Toggle */}
        <button
          type="button"
          onClick={() => setUseStreaming(!useStreaming)}
          className={`neo-badge ${useStreaming ? 'badge-green' : 'badge-yellow'}`}
          style={{ height: '48px', padding: '0 12px', cursor: 'pointer', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}
          title={useStreaming ? "Server-Sent Events streaming enabled" : "Synchronous JSON mode"}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.7rem' }}>
            <Radio size={12} /> {useStreaming ? 'STREAMING' : 'SYNC'}
          </span>
        </button>

        {/* Send Button */}
        <button
          type="submit"
          className="neo-btn neo-btn-primary neo-shadow-md"
          style={{ height: '52px', padding: '0 24px', fontSize: '1rem' }}
          disabled={disabled || !input.trim()}
        >
          <Send size={18} />
          <span>Ask</span>
        </button>
      </form>
    </div>
  );
};
