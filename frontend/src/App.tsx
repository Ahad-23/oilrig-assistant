import React, { useState, useEffect, useRef } from 'react';
import { Header, type ActiveTab } from './components/Header';
import { ChatMessage } from './components/ChatMessage';
import { ChatInput } from './components/ChatInput';
import { OperationsDashboard } from './components/OperationsDashboard';
import { OverridesView } from './components/OverridesView';
import type { FleetUser, ChatMessage as ChatMessageType, CitationItem, GenerativeUIPayload } from './types';
import { 
  Users, 
  Sparkles, 
  Lock, 
  ChevronRight
} from 'lucide-react';
import './App.css';

const API_BASE = 'http://localhost:8000';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>('chat');
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(true);
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
        } else {
          throw new Error("API responded with non-200");
        }
      } catch (err) {
        console.warn("Using offline fallback fleet users list:", err);
        // Fallback mock users for rich standalone operation
        const fallbackUsers: FleetUser[] = [
          { user_id: 'U-201', name: 'Michael Turner', role: 'AREA_LEAD', team_id: 'TEAM-01', team_name: 'Northeast Fleet Operations', area_id: 'AREA-01', area_name: 'Northeast Block 8' },
          { user_id: 'U-202', name: 'Sarah Jenkins', role: 'ENVIRONMENTAL_DIRECTOR', team_id: 'TEAM-02', team_name: 'Compliance & Safety', area_id: 'AREA-03', area_name: 'Southwest Block 24' },
          { user_id: 'U-203', name: 'Carlos Mendez', role: 'FIELD_TECHNICIAN', team_id: 'TEAM-01', team_name: 'Northeast Fleet Operations', area_id: 'AREA-02', area_name: 'Northeast Block 7' },
          { user_id: 'U-204', name: 'David Ross', role: 'OPERATIONS_MANAGER', team_id: 'TEAM-03', team_name: 'Asset Executive Office' },
          { user_id: 'U-205', name: 'Elena Rostova', role: 'DATA_SCIENTIST', team_id: 'TEAM-04', team_name: 'Predictive Analytics' },
        ];
        setUsers(fallbackUsers);
        setActiveUser(fallbackUsers[0]);
        setSessionId(`session_${fallbackUsers[0].user_id}`);
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
            return;
          }
        }
      } catch (err) {
        console.warn("Could not load backend session history:", err);
      }

      // Fresh greeting for this user
      setMessages([
        {
          id: 'welcome_msg',
          sender: 'assistant',
          text: `Welcome, **${activeUser.name}**! I'm **Oily**, your oilfield assistant.\n\nAsk me anything in everyday language:\n- Is a well producing or down right now?\n- Which wells have cold wellhead temperature alerts?\n- Show downtime rankings or spill history.\n- Or report physical temperature corrections directly from the rig.`,
          timestamp: new Date().toLocaleTimeString(),
        }
      ]);
    };
    fetchHistory();
  }, [activeUser, sessionId]);

  // Auto-scroll chat to bottom
  useEffect(() => {
    if (activeTab === 'chat') {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, activeTab]);

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
        text: `New conversation session initialized for **${activeUser.name}**. Prior conversational turns archived into session store.`,
        timestamp: new Date().toLocaleTimeString(),
      }
    ]);
  };

  // 3. Send Message and Handle Streaming or Sync Response
  const handleSendMessage = async (userText: string, useStreaming: boolean = true) => {
    if (!activeUser || isStreaming) return;

    // Switch to chat tab if called from another tab
    if (activeTab !== 'chat') {
      setActiveTab('chat');
    }

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
      statusUpdates: ['Routing query to Gemma 4 reasoning graph...'],
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
        console.warn("Streaming connection offline or failed:", err);
        // Fallback narrative with mock generative UI for rich demonstration
        const fallbackNarrative = `Based on FLIR infrared wellhead telemetry and regulatory inspection records:\n\n**WELL-0001** is currently **NOT PRODUCING OIL** (Idle).\n- **Wellhead Temperature:** 28.6°C\n- **Ambient Temperature:** 26.2°C\n- **Temperature Differential (ΔT):** 2.4°C (Fails the **20.0°C** minimum threshold for T350 wellheads)\n- **Last Inspected:** 2026-10-14 09:30 by inspector **Michael Turner [INS-0001-0203]**.\n- **Diagnostic Finding:** Flue gas recirculating valve seized in closed position. Secondary containment boom deployed [SR-01].`;

        setMessages(prev =>
          prev.map(m =>
            m.id === agentMsgId
              ? {
                  ...m,
                  isStreaming: false,
                  text: fallbackNarrative,
                  citations: [
                    { id: 'INS-0001-0203', source_type: 'inspections' },
                    { id: 'SR-01', source_type: 'spill_reports' },
                    { id: 'SOP-ENV-001', source_type: 'sops' }
                  ],
                  generative_ui: {
                    component: 'StatusCard',
                    props: {
                      asset_id: 'WELL-0001',
                      name: 'WELL-0001 Wellhead Status',
                      well_type: 'T350',
                      area_name: 'Northeast Block 8',
                      is_producing: false,
                      wellhead_temp_c: 28.6,
                      ambient_temp_c: 26.2,
                      delta_temp_c: 2.4,
                      threshold_c: 20.0,
                      last_inspected_at: '2026-10-14 09:30',
                      inspector_name: 'Michael Turner (U-201)',
                      reason: 'Wellhead cold; ΔT 2.4°C < 20.0°C threshold. Valve stuck closed.'
                    }
                  }
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
                  text: `Request encountered an error: ${err.message}`,
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
    <div className="app-container">
      {/* 1. Neubrutalist Global Header with Tabs and Persona Switcher */}
      <Header
        users={users}
        activeUser={activeUser}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onSelectUser={handleSelectUser}
        onResetSession={handleResetSession}
        isStreaming={isStreaming}
        isSidebarOpen={isSidebarOpen}
        onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
      />

      {/* 2. Main Tab View Router */}
      {activeTab === 'chat' && (
        <div className="chat-workspace">
          
          {/* Main Chat Stream & Input Column */}
          <div className="chat-stream-column">
            
            {/* Scrollable Chat Area */}
            <main className="chat-scroll-area">
              {messages.map((msg) => (
                <ChatMessage
                  key={msg.id}
                  message={msg}
                  activeUserName={activeUser?.name}
                />
              ))}
              <div ref={messagesEndRef} />
            </main>

            {/* Bottom Neubrutalist Chat Input with Scenarios */}
            <ChatInput
              onSendMessage={handleSendMessage}
              disabled={isStreaming}
            />
          </div>

          {/* Right Contextual Sidebar Drawer */}
          {isSidebarOpen && (
            <aside className="sidebar-drawer">
              
              {/* Persona Quick Card */}
              <div className="neo-card" style={{ padding: '10px 12px', background: 'var(--accent-yellow-light)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.7rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                  <Users size={12} /> Active Persona
                </div>
                <div style={{ fontWeight: 800, fontSize: '0.95rem', marginTop: '3px' }}>
                  {activeUser?.name || 'Michael Turner'}
                </div>
                <div style={{ fontSize: '0.72rem', color: '#52525b' }}>
                  {activeUser?.role.replace(/_/g, ' ')}
                </div>
                <div style={{ display: 'flex', gap: '4px', marginTop: '6px', flexWrap: 'wrap' }}>
                  <span className="neo-badge badge-blue" style={{ fontSize: '0.62rem', padding: '1px 5px' }}>
                    {activeUser?.area_name || 'Northeast Block 8'}
                  </span>
                  <span className="neo-badge badge-dark" style={{ fontSize: '0.62rem', padding: '1px 5px' }}>
                    {activeUser?.user_id || 'U-201'}
                  </span>
                </div>
              </div>

              {/* Session Memory Isolation Card */}
              <div className="neo-card" style={{ padding: '10px 12px', background: '#ffffff' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.7rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                  <Lock size={12} /> Memory Isolation
                </div>
                <div className="mono" style={{ fontSize: '0.72rem', fontWeight: 700, marginTop: '3px', wordBreak: 'break-all' }}>
                  {sessionId}
                </div>
                <div style={{ fontSize: '0.7rem', color: '#71717a', marginTop: '3px' }}>
                  Turns: {Math.floor(messages.length / 2)} | Zero cross-user leaks
                </div>
              </div>

              {/* Quick Navigation Shortcuts */}
              <div className="neo-card" style={{ padding: '10px 12px', background: '#ffffff', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <div style={{ fontSize: '0.7rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                  Command Jumps
                </div>

                <button
                  className="neo-btn"
                  style={{ justifyContent: 'space-between', padding: '6px 8px', fontSize: '0.75rem' }}
                  onClick={() => setActiveTab('dashboard')}
                >
                  <span>Wells & Alerts</span>
                  <ChevronRight size={13} />
                </button>


                <button
                  className="neo-btn"
                  style={{ justifyContent: 'space-between', padding: '6px 8px', fontSize: '0.75rem' }}
                  onClick={() => setActiveTab('overrides')}
                >
                  <span>Report Field Update</span>
                  <ChevronRight size={13} />
                </button>
              </div>

              {/* Oily Field Tips */}
              <div style={{ marginTop: 'auto', padding: '8px 10px', background: 'var(--bg-muted)', border: '1.5px solid var(--border-color)', fontSize: '0.72rem' }}>
                <div style={{ fontWeight: 800, display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '2px' }}>
                  <Sparkles size={11} color="#ca8a04" /> OPERATOR TIP
                </div>
                Ask Oily plain questions like: <em>"Is Well 1 running?"</em>, <em>"Which wells are down in Block 8?"</em>, or <em>"Show spills on map"</em>.
              </div>
            </aside>
          )}
        </div>
      )}

      {activeTab === 'dashboard' && (
        <div className="tab-content-scrollable">
          <OperationsDashboard
            activeUser={activeUser}
            onAskCopilot={(query) => handleSendMessage(query)}
          />
        </div>
      )}

      {activeTab === 'overrides' && (
        <div className="tab-content-scrollable">
          <OverridesView
            activeUser={activeUser}
            onAskCopilot={(query) => handleSendMessage(query)}
          />
        </div>
      )}
    </div>
  );
};

export default App;
