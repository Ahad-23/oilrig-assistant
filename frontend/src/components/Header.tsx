import { Shield, Users, RefreshCw, Cpu, Activity } from 'lucide-react';
import type { FleetUser } from '../types';

interface HeaderProps {
  users: FleetUser[];
  activeUser: FleetUser | null;
  onSelectUser: (user: FleetUser) => void;
  onResetSession: () => void;
  isStreaming: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  users,
  activeUser,
  onSelectUser,
  onResetSession,
  isStreaming,
}) => {
  return (
    <header
      className="neo-border-thick"
      style={{
        background: '#ffffff',
        padding: '12px 20px',
        boxShadow: 'var(--shadow-md)',
        marginBottom: '20px',
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '12px',
      }}
    >
      {/* Brand Title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div
          className="neo-border"
          style={{
            background: 'var(--accent-yellow)',
            padding: '6px 10px',
            boxShadow: '2px 2px 0px var(--border-color)',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontWeight: 800,
            fontSize: '1.1rem',
            letterSpacing: '0.02em',
          }}
        >
          <Shield size={20} />
          <span>ASSET COPILOT</span>
        </div>
        <div>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            FlytBase Challenge · Hacktoberfest 2026
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
            <span className="neo-badge badge-green" style={{ fontSize: '0.65rem' }}>
              <Activity size={10} /> 200 WELLS ONLINE
            </span>
            <span className="neo-badge badge-purple" style={{ fontSize: '0.65rem' }}>
              <Cpu size={10} /> GOOGLE GEMMA 4
            </span>
          </div>
        </div>
      </div>

      {/* Right Controls: User Switcher & Reset */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
        {/* User Role Switcher Dropdown */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '0.8rem', fontWeight: 700, textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Users size={16} /> Active Persona:
          </span>
          <select
            className="neo-border neo-shadow-sm"
            style={{
              padding: '6px 12px',
              fontFamily: 'var(--font-sans)',
              fontWeight: 600,
              fontSize: '0.85rem',
              background: 'var(--accent-yellow-light)',
              cursor: 'pointer',
              outline: 'none',
            }}
            value={activeUser?.user_id || 'U-201'}
            onChange={(e) => {
              const selected = users.find((u) => u.user_id === e.target.value);
              if (selected) onSelectUser(selected);
            }}
            disabled={isStreaming}
          >
            {users.map((u, idx) => (
              <option key={`${u.user_id}-${idx}`} value={u.user_id}>
                {u.name} ({u.role.replace(/_/g, ' ')} · {u.user_id})
              </option>
            ))}
          </select>
        </div>

        {/* User Role Tag */}
        {activeUser && (
          <div className="neo-badge badge-blue" style={{ fontSize: '0.75rem', padding: '6px 10px' }}>
            {activeUser.area_name || activeUser.team_name || 'Fleet'}
          </div>
        )}

        {/* Clear / New Session Button */}
        <button
          className="neo-btn"
          style={{ padding: '6px 12px', fontSize: '0.8rem' }}
          onClick={onResetSession}
          title="Reset conversation state for this user"
          disabled={isStreaming}
        >
          <RefreshCw size={14} /> New Chat
        </button>
      </div>
    </header>
  );
};
