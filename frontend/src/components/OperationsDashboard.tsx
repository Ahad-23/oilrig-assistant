import React, { useState } from 'react';
import { 
  Activity, 
  Search, 
  Droplets, 
  Flame, 
  AlertTriangle, 
  CheckCircle2, 
  Clock, 
  ArrowRight,
  TrendingUp
} from 'lucide-react';
import type { FleetUser } from '../types';

interface OperationsDashboardProps {
  activeUser: FleetUser | null;
  onAskCopilot: (query: string) => void;
  onNavigateToMap?: () => void;
}

export const OperationsDashboard: React.FC<OperationsDashboardProps> = ({
  activeUser,
  onAskCopilot,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedArea, setSelectedArea] = useState<string>('all');

  const fleetAreas = [
    { id: 'AREA-01', name: 'Northeast Block 8', wells: 25, lat: 32.4412, lon: -102.1124, status: 'Active Alerts', idle: 4 },
    { id: 'AREA-02', name: 'Northeast Block 7', wells: 25, lat: 32.4105, lon: -102.0911, status: 'Optimal', idle: 2 },
    { id: 'AREA-03', name: 'Southwest Block 24', wells: 25, lat: 32.1892, lon: -102.4512, status: 'Spill Attention', idle: 3 },
    { id: 'AREA-04', name: 'Sweetwater Lease Alpha', wells: 25, lat: 32.3321, lon: -102.2198, status: 'Thermal Warning', idle: 5 },
    { id: 'AREA-05', name: 'Midland Basin Section 12', wells: 25, lat: 32.2210, lon: -102.1843, status: 'Optimal', idle: 1 },
    { id: 'AREA-06', name: 'Delaware West Ridge', wells: 25, lat: 32.5512, lon: -102.6102, status: 'Active Alerts', idle: 4 },
    { id: 'AREA-07', name: 'Permian South Sector 9', wells: 25, lat: 32.0911, lon: -102.3411, status: 'Optimal', idle: 2 },
    { id: 'AREA-08', name: 'Central Uplift Block 3', wells: 25, lat: 32.3114, lon: -102.3912, status: 'Optimal', idle: 1 },
  ];

  const sampleWells = [
    {
      id: 'WELL-0001',
      name: 'WELL-0001 (Sweetwater Unit 1)',
      area: 'Northeast Block 8',
      type: 'T350',
      status: 'IDLE (NOT PRODUCING)',
      isProducing: false,
      deltaT: 2.4,
      threshold: 20.0,
      wellheadT: 28.6,
      ambientT: 26.2,
      lastInspection: '2026-10-14 09:30',
      inspector: 'Michael Turner (U-201)',
      issue: 'Wellhead cold; ΔT 2.4°C < 20.0°C threshold. Flue gas valve closed.'
    },
    {
      id: 'WELL-0002',
      name: 'WELL-0002 (Sweetwater Unit 2)',
      area: 'Northeast Block 8',
      type: 'T350',
      status: 'PRODUCING',
      isProducing: true,
      deltaT: 24.8,
      threshold: 20.0,
      wellheadT: 51.2,
      ambientT: 26.4,
      lastInspection: '2026-10-15 14:10',
      inspector: 'David Ross (U-204)',
      issue: 'Operating normally within thermal parameters.'
    },
    {
      id: 'WELL-0012',
      name: 'WELL-0012 (Southwest Ridge)',
      area: 'Southwest Block 24',
      type: 'T400',
      status: 'PRODUCING',
      isProducing: true,
      deltaT: 18.2,
      threshold: 15.0,
      wellheadT: 44.1,
      ambientT: 25.9,
      lastInspection: '2026-10-16 11:20',
      inspector: 'Sarah Jenkins (U-202)',
      issue: 'Minor oil seepage on casing; containment booming deployed.'
    },
    {
      id: 'WELL-0045',
      name: 'WELL-0045 (Midland Spur)',
      area: 'Midland Basin Section 12',
      type: 'T350',
      status: 'IDLE (SHUT-IN)',
      isProducing: false,
      deltaT: 0.8,
      threshold: 20.0,
      wellheadT: 27.0,
      ambientT: 26.2,
      lastInspection: '2026-10-12 16:45',
      inspector: 'Elena Rostova (U-205)',
      issue: 'Downhole pump cavitation. Maintenance work order pending.'
    }
  ];

  const filteredWells = sampleWells.filter(w => {
    const matchesSearch = w.id.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          w.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          w.area.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesArea = selectedArea === 'all' || w.area === selectedArea;
    return matchesSearch && matchesArea;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', paddingBottom: '30px' }}>
      
      {/* 1. Header Banner */}
      <div 
        className="neo-card" 
        style={{ 
          background: 'var(--accent-yellow)', 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center', 
          flexWrap: 'wrap', 
          gap: '12px' 
        }}
      >
        <div>
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center', marginBottom: '6px' }}>
            <span className="neo-badge badge-dark">🛢️ RIG OVERVIEW</span>
            {activeUser && (
              <span className="neo-badge badge-blue">
                OPERATOR: {activeUser.name}
              </span>
            )}
          </div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 900 }}>
            Wellhead Status & Rig Alerts
          </h2>
          <p style={{ fontWeight: 600, color: '#27272a', marginTop: '2px', fontSize: '0.9rem' }}>
            Live oil producing status, cold wellhead temperature warnings, and daily field inspection logs.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button 
            className="neo-btn neo-btn-dark"
            onClick={() => onAskCopilot("Show me a summary table of all non-producing wells across all areas")}
          >
            <Activity size={15} /> Check Idle Wells
          </button>
          <button 
            className="neo-btn" 
            style={{ background: '#ffffff' }}
            onClick={() => onAskCopilot("List all critical wellhead temperature alarms and active spills requiring immediate operator attention.")}
          >
            <AlertTriangle size={15} color="#dc2626" /> View Critical Alarms
          </button>
        </div>
      </div>

      {/* 2. Four Key Neubrutalist Metric Cards */}
      <div className="neo-grid-dashboard">
        {/* Metric 1 */}
        <div className="neo-card neo-card-interactive" style={{ background: '#ffffff' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
              Active Oil Wells
            </span>
            <span className="neo-badge badge-green">200 MONITORED</span>
          </div>
          <div style={{ fontSize: '2.4rem', fontWeight: 800, margin: '8px 0 4px 0' }}>
            178 / 200
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', fontWeight: 600 }}>
            <CheckCircle2 size={14} color="#16a34a" />
            <span>89% Producing Oil</span>
          </div>
          <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '2px dashed #e4e4e7', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            22 wells idle, cold, or shut-in
          </div>
        </div>

        {/* Metric 2 */}
        <div className="neo-card neo-card-interactive" style={{ background: '#ffffff' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
              Cold Wellhead Warnings
            </span>
            <span className="neo-badge badge-red">18 COLD</span>
          </div>
          <div style={{ fontSize: '2.4rem', fontWeight: 800, margin: '8px 0 4px 0', color: 'var(--accent-red)' }}>
            18
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', fontWeight: 600 }}>
            <Flame size={14} color="#dc2626" />
            <span>Low Temperature Delta (ΔT)</span>
          </div>
          <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '2px dashed #e4e4e7', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Crew inspection recommended
          </div>
        </div>

        {/* Metric 3 */}
        <div className="neo-card neo-card-interactive" style={{ background: '#ffffff' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
              Reported Leaks & Spills
            </span>
            <span className="neo-badge badge-yellow">3 ACTIVE</span>
          </div>
          <div style={{ fontSize: '2.4rem', fontWeight: 800, margin: '8px 0 4px 0' }}>
            14.2 <span style={{ fontSize: '1rem', fontWeight: 700 }}>Barrels</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', fontWeight: 600 }}>
            <Droplets size={14} color="#d97706" />
            <span>Clean-up & Booming Tracked</span>
          </div>
          <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '2px dashed #e4e4e7', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Containment procedures active
          </div>
        </div>

        {/* Metric 4 */}
        <div className="neo-card neo-card-interactive" style={{ background: 'var(--accent-blue-light)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
              Oily Accuracy
            </span>
            <span className="neo-badge badge-purple">VERIFIED</span>
          </div>
          <div style={{ fontSize: '2.4rem', fontWeight: 800, margin: '8px 0 4px 0' }}>
            100%
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', fontWeight: 600 }}>
            <CheckCircle2 size={14} color="#16a34a" />
            <span>Backed by Official Logs</span>
          </div>
          <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '2px dashed var(--border-color)', fontSize: '0.75rem' }}>
            Every answer points to real field records
          </div>
        </div>
      </div>

      {/* 3. Fleet Areas Breakdown Grid */}
      <div className="neo-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
          <div>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 800 }}>Geographic Production Areas (8 Sectors)</h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Select an area to filter wells or ask Oily to investigate.</p>
          </div>
          <button 
            className="neo-btn neo-btn-primary"
            style={{ fontSize: '0.8rem', padding: '6px 12px' }}
            onClick={() => onAskCopilot("Show a comparison bar chart of total downtime hours across all 8 geographic areas in the last 4 months")}
          >
            <TrendingUp size={14} /> Compare Area Downtime
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
          {fleetAreas.map((area) => (
            <div 
              key={area.id}
              className="neo-card neo-card-interactive"
              style={{ 
                padding: '14px', 
                background: selectedArea === area.name ? 'var(--accent-yellow-light)' : '#ffffff',
                cursor: 'pointer'
              }}
              onClick={() => setSelectedArea(selectedArea === area.name ? 'all' : area.name)}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <span className="neo-badge badge-dark">{area.id}</span>
                <span className={`neo-badge ${area.idle > 2 ? 'badge-red' : 'badge-green'}`}>
                  {area.idle} IDLE
                </span>
              </div>

              <div style={{ fontWeight: 800, fontSize: '1.05rem', marginTop: '8px' }}>
                {area.name}
              </div>

              <div className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                📍 {area.lat.toFixed(4)}, {area.lon.toFixed(4)}
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '12px', paddingTop: '10px', borderTop: '1.5px dashed #e4e4e7' }}>
                <span style={{ fontSize: '0.8rem', fontWeight: 700 }}>{area.wells} Wells Total</span>
                <button 
                  className="neo-btn" 
                  style={{ padding: '4px 8px', fontSize: '0.7rem' }}
                  onClick={(e) => {
                    e.stopPropagation();
                    onAskCopilot(`Which wells in ${area.name} are not producing oil right now, and why? Show them in a table.`);
                  }}
                >
                  Inspect Area <ArrowRight size={12} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 4. Well Inspector & Quick Search */}
      <div className="neo-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 800 }}>Interactive Well Inspector</h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Real-time FLIR inspection telemetry, thermal differentials, and downhole diagnostics.
            </p>
          </div>

          {/* Search Box */}
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', width: '100%', maxWidth: '360px' }}>
            <div style={{ position: 'relative', flex: 1 }}>
              <input
                type="text"
                className="neo-input"
                style={{ paddingLeft: '36px', fontSize: '0.85rem', padding: '8px 12px 8px 36px' }}
                placeholder="Search well ID (e.g. WELL-0001)..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            </div>
            {selectedArea !== 'all' && (
              <button 
                className="neo-btn" 
                style={{ fontSize: '0.75rem', padding: '8px 10px' }}
                onClick={() => setSelectedArea('all')}
              >
                Clear Area Filter
              </button>
            )}
          </div>
        </div>

        {/* Wells Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '14px' }}>
          {filteredWells.map((well) => (
            <div key={well.id} className="neo-card" style={{ background: '#ffffff', display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                  <span className="neo-badge badge-yellow">{well.id}</span>
                  <span className="neo-badge badge-purple">{well.type}</span>
                </div>
                <span className={`neo-badge ${well.isProducing ? 'badge-green' : 'badge-red'}`}>
                  {well.status}
                </span>
              </div>

              <div>
                <div style={{ fontWeight: 800, fontSize: '1.05rem' }}>{well.name}</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>📍 {well.area}</div>
              </div>

              {/* Sensor Readout Pill */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '6px', background: 'var(--bg-muted)', padding: '8px', border: '2px solid var(--border-color)' }}>
                <div>
                  <div style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--text-muted)' }}>WELLHEAD T</div>
                  <div className="mono" style={{ fontWeight: 800, fontSize: '0.95rem' }}>{well.wellheadT}°C</div>
                </div>
                <div>
                  <div style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--text-muted)' }}>AMBIENT T</div>
                  <div className="mono" style={{ fontWeight: 800, fontSize: '0.95rem' }}>{well.ambientT}°C</div>
                </div>
                <div>
                  <div style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--text-muted)' }}>DELTA ΔT</div>
                  <div className="mono" style={{ fontWeight: 800, fontSize: '0.95rem', color: well.deltaT < well.threshold ? 'var(--accent-red)' : 'inherit' }}>
                    {well.deltaT}°C
                  </div>
                </div>
              </div>

              <div style={{ fontSize: '0.78rem', color: '#3f3f46', background: '#fefce8', padding: '8px', border: '1.5px solid var(--border-color)' }}>
                <strong>Diagnostic Note:</strong> {well.issue}
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'auto', paddingTop: '8px', borderTop: '1px dashed #e4e4e7' }}>
                <span className="mono" style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                  <Clock size={11} style={{ display: 'inline', marginRight: '4px' }} />
                  {well.lastInspection}
                </span>
                <button
                  className="neo-btn neo-btn-primary"
                  style={{ fontSize: '0.75rem', padding: '6px 10px' }}
                  onClick={() => onAskCopilot(`Is ${well.id} producing oil right now? When was it last inspected, and by whom? Show me its status card.`)}
                >
                  Ask Oily
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
