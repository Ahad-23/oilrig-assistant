import React from 'react';
import { User, Droplet, Loader2, Sparkles } from 'lucide-react';
import type { ChatMessage as ChatMessageType } from '../types';
import { OpenUIRenderer } from './widgets/OpenUIRenderer';
import { CitationsList } from './CitationsList';

interface ChatMessageProps {
  message: ChatMessageType;
  activeUserName?: string;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ message, activeUserName }) => {
  const isUser = message.sender === 'user';

  // Format text to highlight bracketed citations, bold words, and bullet points
  const renderFormattedText = (text: string) => {
    if (!text) return null;

    const lines = text.split('\n');

    return lines.map((line, lIdx) => {
      const isBullet = line.trim().startsWith('- ') || line.trim().startsWith('* ');
      const cleanLine = isBullet ? line.trim().substring(2) : line;

      // Highlight bracketed citations like [INS-0001-0203] or [SR-01]
      const parts = cleanLine.split(/(\[[A-Za-z0-9-—§. ]+\])/g);

      const content = parts.map((part, pIdx) => {
        if (/^\[.+\]$/.test(part)) {
          return (
            <span 
              key={pIdx} 
              className="neo-badge badge-blue mono" 
              style={{ fontSize: '0.74rem', margin: '0 2px', verticalAlign: 'middle', padding: '1px 6px' }}
              title="Verifiable Citation Grounding"
            >
              {part}
            </span>
          );
        }

        // Bold formatting **text**
        const boldParts = part.split(/(\*\*[^*]+\*\*)/g);
        return boldParts.map((bPart, bIdx) => {
          if (bPart.startsWith('**') && bPart.endsWith('**')) {
            return <strong key={bIdx} style={{ fontWeight: 800 }}>{bPart.slice(2, -2)}</strong>;
          }
          return bPart;
        });
      });

      if (isBullet) {
        return (
          <div key={lIdx} style={{ display: 'flex', gap: '8px', margin: '4px 0', paddingLeft: '8px' }}>
            <span style={{ fontWeight: 800, color: '#000' }}>•</span>
            <div style={{ flex: 1 }}>{content}</div>
          </div>
        );
      }

      return (
        <p key={lIdx} style={{ margin: line.trim() ? '5px 0' : '4px 0', minHeight: line.trim() ? 'auto' : '4px' }}>
          {content}
        </p>
      );
    });
  };

  // 1. Sleek, Proportionate User Speech Card
  if (isUser) {
    return (
      <div
        style={{
          display: 'flex',
          gap: '10px',
          margin: '6px 0',
          alignItems: 'flex-start',
          flexDirection: 'row-reverse',
          width: '100%',
        }}
      >
        {/* User Stamp Avatar */}
        <div
          className="neo-border"
          style={{
            width: '32px',
            height: '32px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'var(--accent-yellow)',
            color: '#000000',
            boxShadow: 'var(--shadow-xs)',
            flexShrink: 0,
            marginTop: '2px',
          }}
          title={activeUserName || 'Operator'}
        >
          <User size={16} />
        </div>

        {/* User Speech Card */}
        <div
          className="neo-border"
          style={{
            maxWidth: '75%',
            width: 'fit-content',
            minWidth: '160px',
            background: 'var(--accent-yellow-light)',
            boxShadow: 'var(--shadow-sm)',
            padding: '10px 14px',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
          }}
        >
          {/* Header Bar */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '8px',
              borderBottom: '1px solid rgba(0,0,0,0.15)',
              paddingBottom: '3px',
              marginBottom: '2px',
            }}
          >
            <span style={{ fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', color: '#713f12' }}>
              👤 {activeUserName || 'OPERATOR'}
            </span>
            <span className="mono" style={{ fontSize: '0.65rem', color: '#854d0e' }}>
              {message.timestamp}
            </span>
          </div>

          {/* User Query Text */}
          <div style={{ fontSize: '0.92rem', fontWeight: 600, color: '#1c1917', lineHeight: '1.45' }}>
            {message.text}
          </div>
        </div>
      </div>
    );
  }

  // 2. Technical Grounded Assistant Terminal Card
  return (
    <div
      style={{
        display: 'flex',
        gap: '10px',
        margin: '10px 0',
        alignItems: 'flex-start',
        flexDirection: 'row',
        width: '100%',
      }}
    >
      {/* Assistant Stamp Avatar */}
      <div
        className="neo-border"
        style={{
          width: '34px',
          height: '34px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#000000',
          color: 'var(--accent-yellow)',
          boxShadow: 'var(--shadow-xs)',
          flexShrink: 0,
          marginTop: '2px',
        }}
        title="Oily Field Assistant"
      >
        <Droplet size={18} fill="var(--accent-yellow)" />
      </div>

      {/* Assistant Window Card */}
      <div
        className="neo-border-thick"
        style={{
          maxWidth: '96%',
          width: '100%',
          background: '#ffffff',
          boxShadow: 'var(--shadow-md)',
          overflow: 'hidden',
        }}
      >
        {/* Retro Window Titlebar */}
        <div 
          className="neo-window-titlebar"
          style={{
            background: '#121212',
            padding: '5px 12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontWeight: 900, letterSpacing: '0.04em' }}>
              🛢️ OILY
            </span>
            <span className="neo-badge badge-green" style={{ fontSize: '0.6rem', padding: '1px 5px' }}>
              VERIFIED FIELD DATA
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="mono" style={{ fontSize: '0.65rem', color: '#a1a1aa' }}>
              {message.timestamp}
            </span>
            <div className="neo-window-dots">
              <span className="neo-window-dot" style={{ background: '#ef4444' }} />
              <span className="neo-window-dot" style={{ background: '#eab308' }} />
              <span className="neo-window-dot" style={{ background: '#22c55e' }} />
            </div>
          </div>
        </div>

        {/* Message Content Body */}
        <div style={{ padding: '14px 16px' }}>
          
          {/* Streaming Status Pill */}
          {message.isStreaming && message.statusUpdates && message.statusUpdates.length > 0 && (
            <div
              style={{
                padding: '6px 10px',
                background: 'var(--accent-yellow-light)',
                border: '1.5px solid var(--border-color)',
                marginBottom: '10px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '0.78rem',
                fontWeight: 700,
                boxShadow: 'var(--shadow-xs)',
              }}
            >
              <Loader2 size={13} className="animate-spin" />
              <span>{message.statusUpdates[message.statusUpdates.length - 1]}</span>
            </div>
          )}

          {/* Narrative Text */}
          <div style={{ fontSize: '0.925rem', lineHeight: '1.6', color: '#18181b' }}>
            {renderFormattedText(message.text)}
          </div>

          {/* Inline Generative UI Component */}
          {message.generative_ui && (
            <div style={{ marginTop: '14px', width: '100%', overflowX: 'auto' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
                <span className="neo-badge badge-purple" style={{ fontSize: '0.65rem', padding: '2px 6px' }}>
                  <Sparkles size={10} /> GENERATIVE UI WIDGET
                </span>
              </div>
              <OpenUIRenderer payload={message.generative_ui} />
            </div>
          )}

          {/* Verifiable Citations */}
          {message.citations && message.citations.length > 0 && (
            <CitationsList citations={message.citations} />
          )}
        </div>
      </div>
    </div>
  );
};
