import { useState, useEffect, useRef } from 'react';
import { Header } from './components/Header';
import { ChatMessage } from './components/ChatMessage';
import { ChatInput } from './components/ChatInput';
import type { FleetUser, ChatMessage as ChatMessageType, CitationItem, GenerativeUIPayload } from './types';

const API_BASE = 'http://localhost:8000';

export const App: React.FC = () => {
  const [users, setUsers] = useState<FleetUser[]>([]);
  const [activeUser, setActiveUser] = useState<FleetUser | null>(null);
  const [sessionId, setSessionId] = useState<string>('default_session');
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 1. Fetch Fleet Users on Mount
  useEffect(() => {
    const fetchUsers = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/users`);
        if (res.ok) {
          const userList: FleetUser[] = await res.json();
          setUsers(userList);
          // Set Michael Turner (U-201) as initial default
          const defaultUser = userList.find(u => u.user_id === 'U-201') || userList[0];
          if (defaultUser) {
            setActiveUser(defaultUser);
            setSessionId(`session_${defaultUser.user_id}`);
          }
        }
      } catch (err) {
        console.error("Failed to connect to API backend:", err);
      }
    };
    fetchUsers();
  }, []);

  // 2. Fetch Isolated Session History when Active User or Session Changes
  useEffect(() => {
    if (!activeUser) return;
    const fetchHistory = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/history/${activeUser.user_id}/${sessionId}`);
        if (res.ok) {
          const turns = await res.json();
          if (turns && turns.length > 0) {
            const formatted: ChatMessageType[] = [];
            turns.forEach((t: any, idx: number) => {
              formatted.push({
                id: `hist_user_${idx}`,
                sender: 'user',
                text: t.user_query,
                timestamp: t.timestamp ? new Date(t.timestamp).toLocaleTimeString() : 'Earlier',
              });
              formatted.push({
                id: `hist_agent_${idx}`,
                sender: 'assistant',
                text: t.narrative_response,
                timestamp: t.timestamp ? new Date(t.timestamp).toLocaleTimeString() : 'Earlier',
              });
            });
            setMessages(formatted);
          } else {
            // Fresh greeting for this user
            setMessages([
              {
                id: 'welcome_msg',
                sender: 'assistant',
                text: `Welcome, **${activeUser.name}** (${activeUser.role.replace(/_/g, ' ')}). I am the Asset Intelligence Copilot for onshore field operations. You can ask me about wellhead production status, downtime accounting, temperature differentials, regulatory spill compliance, or input operational corrections.`,
                timestamp: new Date().toLocaleTimeString(),
              }
            ]);
          }
        }
      } catch (err) {
        console.error("Failed to load session history:", err);
      }
    };
    fetchHistory();
  }, [activeUser, sessionId]);

  // Auto-scroll chat to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Handle switching active user persona
  const handleSelectUser = (user: FleetUser) => {
    setActiveUser(user);
    setSessionId(`session_${user.user_id}`);
  };

  // Reset conversation session for current user
  const handleResetSession = async () => {
    if (!activeUser) return;
    try {
      await fetch(`${API_BASE}/api/history/clear?user_id=${activeUser.user_id}&session_id=${sessionId}`, {
        method: 'POST'
      });
    } catch (e) {
      // Ignore
    }
    const newSessionId = `session_${activeUser.user_id}_${Date.now()}`;
    setSessionId(newSessionId);
    setMessages([
      {
        id: `reset_${Date.now()}`,
        sender: 'assistant',
        text: `New conversation initialized for **${activeUser.name}**. Prior conversational turns have been archived.`,
        timestamp: new Date().toLocaleTimeString(),
      }
    ]);
  };

  // 3. Send Message and Handle Streaming or Sync Response
  const handleSendMessage = async (userText: string, useStreaming: boolean = true) => {
    if (!activeUser || isStreaming) return;

    const userMsgId = `user_${Date.now()}`;
    const agentMsgId = `agent_${Date.now()}`;
    const userMessage: ChatMessageType = {
      id: userMsgId,
      sender: 'user',
      text: userText,
      timestamp: new Date().toLocaleTimeString(),
    };

    const initialAgentMessage: ChatMessageType = {
      id: agentMsgId,
      sender: 'assistant',
      text: '',
      timestamp: new Date().toLocaleTimeString(),
      statusUpdates: ['Contacting copilot reasoning engine...'],
      isStreaming: true,
    };

    setMessages(prev => [...prev, userMessage, initialAgentMessage]);
    setIsStreaming(true);

    if (useStreaming) {
      // --- SSE Streaming Mode ---
      try {
        const response = await fetch(`${API_BASE}/api/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: userText,
            user_id: activeUser.user_id,
            session_id: sessionId,
            stream: true,
          }),
        });

        if (!response.ok || !response.body) {
          throw new Error(`Streaming failed: HTTP ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let accumulatedNarrative = '';
        let extractedCitations: CitationItem[] = [];
        let extractedUI: GenerativeUIPayload | null = null;
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          let currentEvent = '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith('event:')) {
              currentEvent = trimmed.replace('event:', '').trim();
            } else if (trimmed.startsWith('data:')) {
              const rawData = trimmed.replace('data:', '').trim();
              try {
                const parsedData = JSON.parse(rawData);

                if (currentEvent === 'status') {
                  const statusMsg = parsedData.message || 'Processing query...';
                  setMessages(prev =>
                    prev.map(m =>
                      m.id === agentMsgId
                        ? { ...m, statusUpdates: [...(m.statusUpdates || []), statusMsg] }
                        : m
                    )
                  );
                } else if (currentEvent === 'token') {
                  accumulatedNarrative += parsedData.token || '';
                  setMessages(prev =>
                    prev.map(m =>
                      m.id === agentMsgId
                        ? { ...m, text: accumulatedNarrative }
                        : m
                    )
                  );
                } else if (currentEvent === 'citations') {
                  extractedCitations = Array.isArray(parsedData) ? parsedData : [];
                  setMessages(prev =>
                    prev.map(m =>
                      m.id === agentMsgId
                        ? { ...m, citations: extractedCitations }
                        : m
                    )
                  );
                } else if (currentEvent === 'generative_ui') {
                  extractedUI = parsedData;
                  setMessages(prev =>
                    prev.map(m =>
                      m.id === agentMsgId
                        ? { ...m, generative_ui: extractedUI }
                        : m
                    )
                  );
                } else if (currentEvent === 'done') {
                  if (parsedData.narrative && !accumulatedNarrative) {
                    accumulatedNarrative = parsedData.narrative;
                  }
                  setMessages(prev =>
                    prev.map(m =>
                      m.id === agentMsgId
                        ? {
                            ...m,
                            text: accumulatedNarrative || parsedData.narrative,
                            isStreaming: false,
                          }
                        : m
                    )
                  );
                }
              } catch (e) {
                // Ignore raw data parsing errors
              }
            }
          }
        }

        // Finalize message state
        setMessages(prev =>
          prev.map(m =>
            m.id === agentMsgId
              ? { ...m, isStreaming: false, text: accumulatedNarrative || m.text }
              : m
          )
        );
      } catch (err: any) {
        console.error("Streaming error:", err);
        setMessages(prev =>
          prev.map(m =>
            m.id === agentMsgId
              ? {
                  ...m,
                  isStreaming: false,
                  text: `An error occurred while streaming response: ${err.message}`,
                }
              : m
          )
        );
      } finally {
        setIsStreaming(false);
      }
    } else {
      // --- Synchronous Mode ---
      try {
        const response = await fetch(`${API_BASE}/api/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: userText,
            user_id: activeUser.user_id,
            session_id: sessionId,
          }),
        });

        if (!response.ok) {
          throw new Error(`Sync call failed with status ${response.status}`);
        }

        const data = await response.json();
        setMessages(prev =>
          prev.map(m =>
            m.id === agentMsgId
              ? {
                  ...m,
                  text: data.narrative,
                  citations: data.citations,
                  generative_ui: data.generative_ui,
                  isStreaming: false,
                }
              : m
          )
        );
      } catch (err: any) {
        setMessages(prev =>
          prev.map(m =>
            m.id === agentMsgId
              ? {
                  ...m,
                  isStreaming: false,
                  text: `Request failed: ${err.message}`,
                }
              : m
          )
        );
      } finally {
        setIsStreaming(false);
      }
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        maxWidth: '1280px',
        margin: '0 auto',
        padding: '16px',
      }}
    >
      {/* Neobrutalist Header with Persona Switcher */}
      <Header
        users={users}
        activeUser={activeUser}
        onSelectUser={handleSelectUser}
        onResetSession={handleResetSession}
        isStreaming={isStreaming}
      />

      {/* Main Chat Scroll View */}
      <main
        className="neo-border-thick"
        style={{
          flex: 1,
          overflowY: 'auto',
          background: '#ffffff',
          boxShadow: 'var(--shadow-md)',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {messages.map((msg) => (
          <ChatMessage
            key={msg.id}
            message={msg}
            activeUserName={activeUser?.name}
          />
        ))}
        <div ref={messagesEndRef} />
      </main>

      {/* Neobrutalist Input & Scenario Buttons */}
      <ChatInput
        onSendMessage={handleSendMessage}
        disabled={isStreaming}
      />
    </div>
  );
};

export default App;
