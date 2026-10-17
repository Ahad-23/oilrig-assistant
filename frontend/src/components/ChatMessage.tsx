import { User, Cpu, Loader2 } from 'lucide-react';
import type { ChatMessage as ChatMessageType } from '../types';
import { OpenUIRenderer } from './widgets/OpenUIRenderer';
import { CitationsList } from './CitationsList';

interface ChatMessageProps {
  message: ChatMessageType;
  activeUserName?: string;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ message, activeUserName }) => {
  const isUser = message.sender === 'user';

  // Format text to highlight bracketed citations and bold words cleanly
  const renderFormattedText = (text: string) => {
    if (!text) return null;

    // Split text by lines
    const lines = text.split('\n');

    return lines.map((line, lIdx) => {
      // Check for bullet list item
      const isBullet = line.trim().startsWith('- ') || line.trim().startsWith('* ');
      const cleanLine = isBullet ? line.trim().substring(2) : line;

      // Highlight bracketed citations like [INS-0001-0203] or [SR-01]
      const parts = cleanLine.split(/(\[[A-Za-z0-9-—§. ]+\])/g);

      const content = parts.map((part, pIdx) => {
        if (/^\[.+\]$/.test(part)) {
          return (
            <span key={pIdx} className="neo-badge badge-blue mono" style={{ fontSize: '0.8rem', margin: '0 2px' }}>
              {part}
            </span>
          );
        }

        // Bold formatting **text**
        const boldParts = part.split(/(\*\*[^*]+\*\*)/g);
        return boldParts.map((bPart, bIdx) => {
          if (bPart.startsWith('**') && bPart.endsWith('**')) {
            return <strong key={bIdx}>{bPart.slice(2, -2)}</strong>;
          }
          return bPart;
        });
      });

      if (isBullet) {
        return (
          <div key={lIdx} style={{ display: 'flex', gap: '8px', margin: '4px 0', paddingLeft: '8px' }}>
            <span style={{ fontWeight: 800 }}>•</span>
            <div style={{ flex: 1 }}>{content}</div>
          </div>
        );
      }

      return (
        <p key={lIdx} style={{ margin: line.trim() ? '6px 0' : '8px 0', minHeight: line.trim() ? 'auto' : '8px' }}>
          {content}
        </p>
      );
    });
  };

  return (
    <div
      style={{
        display: 'flex',
        gap: '12px',
        margin: '18px 0',
        alignItems: 'flex-start',
        flexDirection: isUser ? 'row-reverse' : 'row',
      }}
    >
      {/* Sender Avatar */}
      <div
        className="neo-border"
        style={{
          width: '38px',
          height: '38px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: isUser ? 'var(--accent-yellow)' : '#000000',
          color: isUser ? '#000000' : '#ffffff',
          boxShadow: '2px 2px 0px var(--border-color)',
          flexShrink: 0,
        }}
      >
        {isUser ? <User size={18} /> : <Cpu size={18} />}
      </div>

      {/* Message Bubble Container */}
      <div
        className="neo-card neo-shadow-sm"
        style={{
          maxWidth: '85%',
          background: isUser ? '#ffffff' : 'var(--bg-card)',
          borderColor: 'var(--border-color)',
          padding: '16px',
        }}
      >
        {/* Header Label */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '8px',
            marginBottom: '6px',
            borderBottom: '1px solid #e4e4e7',
            paddingBottom: '4px',
          }}
        >
          <span style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase' }}>
            {isUser ? (activeUserName || 'Operator') : 'Asset Intelligence Copilot (Gemma 4)'}
          </span>
          <span className="mono" style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
            {message.timestamp}
          </span>
        </div>

        {/* Streaming Status Indicator */}
        {message.isStreaming && message.statusUpdates && message.statusUpdates.length > 0 && (
          <div
            style={{
              padding: '6px 10px',
              background: 'var(--accent-blue-light)',
              border: '1.5px solid var(--border-color)',
              marginBottom: '10px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              fontSize: '0.8rem',
              fontWeight: 600,
            }}
          >
            <Loader2 size={14} className="animate-spin" />
            <span>{message.statusUpdates[message.statusUpdates.length - 1]}</span>
          </div>
        )}

        {/* Narrative Response */}
        <div style={{ fontSize: '0.925rem', lineHeight: '1.55' }}>
          {renderFormattedText(message.text)}
        </div>

        {/* Inline Generative UI Component */}
        {message.generative_ui && (
          <div style={{ marginTop: '12px' }}>
            <OpenUIRenderer payload={message.generative_ui} />
          </div>
        )}

        {/* Verifiable Citations */}
        {message.citations && message.citations.length > 0 && (
          <CitationsList citations={message.citations} />
        )}
      </div>
    </div>
  );
};
