import React, { useState } from 'react';
import { 
  Droplet, 
  Users, 
  RefreshCw, 
  Menu, 
  X, 
  MessageSquare, 
  BarChart3, 
  SlidersHorizontal,
  PanelRightClose,
  PanelRightOpen
} from 'lucide-react';
import type { FleetUser } from '../types';

export type ActiveTab = 'chat' | 'dashboard' | 'overrides';

interface HeaderProps {
  users: FleetUser[];
  activeUser: FleetUser | null;
  activeTab: ActiveTab;
  onTabChange: (tab: ActiveTab) => void;
  onSelectUser: (user: FleetUser) => void;
  onResetSession: () => void;
  isStreaming: boolean;
  isSidebarOpen?: boolean;
  onToggleSidebar?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  users,
  activeUser,
  activeTab,
  onTabChange,
  onSelectUser,
  onResetSession,
  isStreaming,
  isSidebarOpen = true,
  onToggleSidebar,
}) => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const tabs: { id: ActiveTab; label: string; icon: React.ReactNode }[] = [
    { id: 'chat', label: 'Oily Chat', icon: <MessageSquare size={15} /> },
    { id: 'dashboard', label: 'Wells & Alerts', icon: <BarChart3 size={15} /> },
    { id: 'overrides', label: 'Report Field Update', icon: <SlidersHorizontal size={15} /> },
  ];

  return (
    <div style={{ flexShrink: 0 }}>
      {/* 1. Neubrutalist Marquee Operational Ticker (Layman / Field Crew Friendly) */}
      <div className="neo-ticker-wrap" style={{ padding: '4px 0', fontSize: '0.72rem' }}>
        <div className="neo-ticker">
          <span>🟢 200 OIL WELLS MONITORED IN REAL-TIME</span>
          <span>🛢️ OILY FIELD ASSISTANT READY FOR OPERATORS</span>
          <span>⚠️ 18 WELLHEAD TEMPERATURE WARNINGS DETECTED</span>
          <span>📍 SWEETWATER LEASE & PERMIAN BASIN ONLINE</span>
          <span>📋 ALL ANSWERS BACKED BY VERIFIED FIELD LOGS</span>
          <span>🟢 200 OIL WELLS MONITORED IN REAL-TIME</span>
          <span>🛢️ OILY FIELD ASSISTANT READY FOR OPERATORS</span>
          <span>⚠️ 18 WELLHEAD TEMPERATURE WARNINGS DETECTED</span>
        </div>
      </div>

      {/* 2. Main Neubrutalist Navigation Bar */}
      <header
        className="neo-border-thick"
        style={{
          background: '#ffffff',
          padding: '8px 14px',
          boxShadow: 'var(--shadow-sm)',
          margin: '6px 0 10px 0',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '10px',
            flexWrap: 'nowrap',
          }}
        >
          {/* Brand Logo: OILY */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
            <div
              className="neo-border"
              style={{
                background: 'var(--accent-yellow)',
                padding: '6px 12px',
                boxShadow: 'var(--shadow-xs)',
                display: 'flex',
                alignItems: 'center',
                gap: '7px',
                fontWeight: 900,
                fontSize: '1.15rem',
                letterSpacing: '0.04em',
              }}
            >
              <Droplet size={19} fill="#000" />
              <span>OILY</span>
            </div>
            
            <div className="hide-mobile">
              <span className="neo-badge badge-green" style={{ fontSize: '0.62rem', padding: '1px 6px' }}>
                <span className="pulse-dot" style={{ background: '#000', width: '6px', height: '6px' }} />
                RIG LIVE
              </span>
            </div>
          </div>

          {/* Desktop Navigation Tabs */}
          <nav className="hide-mobile nav-tabs-wrapper">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                className={`nav-tab-btn ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => onTabChange(tab.id)}
              >
                {tab.icon}
                <span>{tab.label}</span>
              </button>
            ))}
          </nav>

          {/* Right Controls: Operator Switcher, Sidebar Toggle, Reset, Mobile Hamburger */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
            
            {/* Operator Switcher Dropdown */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span className="hide-mobile" style={{ fontSize: '0.72rem', fontWeight: 800, textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: '3px' }}>
                <Users size={13} />
              </span>
              <select
                className="neo-select"
                style={{
                  fontSize: '0.78rem',
                  padding: '5px 8px',
                  background: 'var(--accent-yellow-light)',
                  maxWidth: '190px',
                }}
                value={activeUser?.user_id || 'U-201'}
                onChange={(e) => {
                  const selected = users.find((u) => u.user_id === e.target.value);
                  if (selected) onSelectUser(selected);
                }}
                disabled={isStreaming}
                title="Select active field operator persona"
              >
                {users.map((u, idx) => (
                  <option key={`${u.user_id}-${idx}`} value={u.user_id}>
                    {u.name} ({u.role.replace(/_/g, ' ')})
                  </option>
                ))}
              </select>
            </div>

            {/* Sidebar Drawer Toggle (Only in Chat tab) */}
            {activeTab === 'chat' && onToggleSidebar && (
              <button
                className="neo-btn hide-mobile"
                style={{ 
                  padding: '5px 8px', 
                  fontSize: '0.72rem',
                  background: isSidebarOpen ? 'var(--bg-muted)' : '#ffffff' 
                }}
                onClick={onToggleSidebar}
                title={isSidebarOpen ? "Collapse operator panel" : "Expand operator panel"}
              >
                {isSidebarOpen ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />}
                <span style={{ fontSize: '0.68rem' }}>Panel</span>
              </button>
            )}

            {/* New Chat / Reset Session */}
            <button
              className="neo-btn hide-mobile"
              style={{ padding: '5px 10px', fontSize: '0.72rem' }}
              onClick={onResetSession}
              title="Start a fresh chat conversation"
              disabled={isStreaming}
            >
              <RefreshCw size={12} />
              <span>New Chat</span>
            </button>

            {/* Mobile Hamburger Toggle */}
            <button
              className="neo-btn hide-desktop"
              style={{ padding: '5px 8px' }}
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-label="Toggle navigation menu"
            >
              {mobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>

        {/* Mobile Sub-Header Tabs */}
        <div className="hide-desktop" style={{ marginTop: '8px', overflowX: 'auto', display: 'flex', gap: '4px', paddingBottom: '2px' }}>
          {tabs.map((tab) => (
            <button
              key={tab.id}
              className={`nav-tab-btn ${activeTab === tab.id ? 'active' : ''}`}
              style={{ padding: '4px 8px', fontSize: '0.72rem' }}
              onClick={() => {
                onTabChange(tab.id);
                setMobileMenuOpen(false);
              }}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </div>
      </header>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className="mobile-nav-drawer" onClick={() => setMobileMenuOpen(false)}>
          <div className="mobile-nav-panel" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: 'var(--neo-border-thick)', paddingBottom: '10px' }}>
              <div style={{ fontWeight: 900, fontSize: '1.1rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Droplet size={18} fill="#000" />
                <span>OILY MENU</span>
              </div>
              <button className="neo-btn" style={{ padding: '3px 6px' }} onClick={() => setMobileMenuOpen(false)}>
                <X size={15} />
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  className={`neo-btn ${activeTab === tab.id ? 'neo-btn-primary' : ''}`}
                  style={{ justifyContent: 'flex-start', padding: '8px 12px' }}
                  onClick={() => {
                    onTabChange(tab.id);
                    setMobileMenuOpen(false);
                  }}
                >
                  {tab.icon}
                  <span>{tab.label}</span>
                </button>
              ))}
            </div>

            <div style={{ borderTop: 'var(--neo-border-thick)', paddingTop: '14px', marginTop: 'auto' }}>
              <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', marginBottom: '6px' }}>
                Active Operator
              </div>
              {activeUser && (
                <div className="neo-card" style={{ padding: '8px', background: 'var(--accent-yellow-light)' }}>
                  <div style={{ fontWeight: 800, fontSize: '0.9rem' }}>{activeUser.name}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{activeUser.role.replace(/_/g, ' ')}</div>
                  <div className="neo-badge badge-blue" style={{ marginTop: '4px', fontSize: '0.62rem' }}>
                    {activeUser.area_name || activeUser.team_name || 'Fleet'}
                  </div>
                </div>
              )}

              <button
                className="neo-btn"
                style={{ width: '100%', marginTop: '10px', fontSize: '0.8rem' }}
                onClick={() => {
                  onResetSession();
                  setMobileMenuOpen(false);
                }}
              >
                <RefreshCw size={13} /> Clear Chat
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
