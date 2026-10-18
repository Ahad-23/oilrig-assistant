import React, { useState } from 'react';
import { Send, Zap, Radio, CornerDownLeft, Sparkles } from 'lucide-react';

interface ChatInputProps {
  onSendMessage: (message: string, useStreaming: boolean) => void;
  disabled: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSendMessage, disabled }) => {
  const [input, setInput] = useState('');
  const [useStreaming, setUseStreaming] = useState(true);

  const quickPrompts = [
    { label: 'Q1. Well Status', prompt: 'Is WELL-0001 producing oil right now? When was it last inspected, and by whom? Show me its status card.' },
    { label: 'Q2. Area Wells Table', prompt: 'Which wells in Northeast Block 8 are not producing oil right now, and why? Show them in a table.' },
    { label: 'Q3. 13-Wk Temp Trend', prompt: "Show a line chart of WELL-0001's wellhead temperature against air temperature for the last 13 weeks, and mark when it was not producing oil." },
    { label: 'Q4. 4-Yr Spills Table', prompt: 'How many oil spills has WELL-0001 had in the last 4 years, and how much oil in total? List them in a table.' },
    { label: 'Q6. Downtime Bar Chart', prompt: 'Which 3 wells in Northeast Block 7 had the most downtime in the last 4 months? Show a bar chart.' },
    { label: 'Q7. Spill Map', prompt: 'Show on a map every well in Northeast Block 8 with a real spill in the last 90 days.' },
    { label: 'Q8. Spills Heatmap', prompt: 'Show a heatmap of 2026 spills by geographic area and month.' },
    { label: 'Q9. Rule Breaches', prompt: 'Which rules has WELL-0001 broken in the last 12 months, and what is still open?' },
    { label: 'Q10. Containment SLA', prompt: 'In Southwest Block 24, which spills in the last 90 days were not contained within the SOP time limit?' },
    { label: 'Q11. Private Memory', prompt: 'For the three wells we discussed earlier, what have repairs cost this year?' },
  ];

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || disabled) return;
    onSendMessage(input.trim(), useStreaming);
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div style={{ paddingTop: '8px', flexShrink: 0 }}>
      
      {/* Sleek Horizontal Quick Scenario Chips */}
      <div 
        style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: '6px', 
          overflowX: 'auto', 
          paddingBottom: '6px',
          marginBottom: '4px',
          scrollbarWidth: 'none'
        }}
      >
        <span 
          style={{ 
            fontSize: '0.68rem', 
            fontWeight: 800, 
            textTransform: 'uppercase', 
            color: 'var(--text-muted)', 
            display: 'flex', 
            alignItems: 'center', 
            gap: '3px', 
            flexShrink: 0,
            paddingRight: '2px'
          }}
        >
          <Zap size={11} /> Quick Prompts:
        </span>
        {quickPrompts.map((qp, idx) => (
          <button
            key={idx}
            className="neo-btn"
            style={{ 
              padding: '3px 8px', 
              fontSize: '0.72rem', 
              whiteSpace: 'nowrap', 
              flexShrink: 0, 
              background: '#ffffff',
              textTransform: 'none',
              gap: '4px',
              borderWidth: '1.5px',
              boxShadow: 'var(--shadow-xs)'
            }}
            onClick={() => onSendMessage(qp.prompt, useStreaming)}
            disabled={disabled}
            title={qp.prompt}
          >
            <Sparkles size={10} color="#ca8a04" />
            <span>{qp.label}</span>
          </button>
        ))}
      </div>

      {/* Main High-Contrast Input Form */}
      <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
        
        {/* Input Text Box */}
        <div style={{ flex: 1, position: 'relative' }}>
          <input
            type="text"
            className="neo-input"
            style={{
              padding: '10px 14px',
              fontSize: '0.92rem',
              fontWeight: 500,
              background: '#ffffff',
              height: '44px',
              boxSizing: 'border-box'
            }}
            placeholder="Ask Oily about wells, cold temperatures, downtime, leaks, or report field updates..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
          />
        </div>

        {/* Streaming / Sync Mode Pill */}
        <button
          type="button"
          onClick={() => setUseStreaming(!useStreaming)}
          className={`neo-badge ${useStreaming ? 'badge-green' : 'badge-yellow'}`}
          style={{ 
            height: '44px', 
            padding: '0 10px', 
            cursor: 'pointer', 
            display: 'flex', 
            justifyContent: 'center',
            alignItems: 'center',
            flexShrink: 0,
            borderWidth: '2px'
          }}
          title={useStreaming ? "Server-Sent Events streaming enabled" : "Synchronous JSON response"}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.68rem', fontWeight: 800 }}>
            <Radio size={11} className={useStreaming ? 'animate-pulse' : ''} />
            <span className="hide-mobile">{useStreaming ? 'STREAM' : 'SYNC'}</span>
          </span>
        </button>

        {/* Send Button */}
        <button
          type="submit"
          className="neo-btn neo-btn-primary"
          style={{ height: '44px', padding: '0 18px', fontSize: '0.9rem', flexShrink: 0 }}
          disabled={disabled || !input.trim()}
        >
          <Send size={15} />
          <span className="hide-mobile">Ask</span>
          <CornerDownLeft size={12} className="hide-mobile" style={{ opacity: 0.6 }} />
        </button>
      </form>
    </div>
  );
};
