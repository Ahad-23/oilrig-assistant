import React, { useState, useEffect, useRef, useMemo } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { 
  Navigation, 
  MapPin, 
  Layers, 
  Compass, 
  Filter, 
  ArrowRight,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Search,
  AlertTriangle,
  Flame,
  CheckCircle2,
  Copy,
  Check,
  Fuel,
  Radio,
  Satellite,
  Map as MapIcon,
  Crosshair
} from 'lucide-react';

interface FleetMapViewProps {
  onAskCopilot: (query: string) => void;
}

export interface MapWell {
  asset_id: string;
  name: string;
  well_type: string;
  area_name: string;
  lat: number;
  lon: number;
  recorded_status: string;
  wellhead_temp_c: number | null;
  ambient_temp_c: number | null;
  delta_temp_c: number | null;
  is_producing: boolean;
  has_active_spill: boolean;
  spill_est_volume_bbl?: number | null;
  latest_notes?: string | null;
  inspected_at?: string | null;
}

export interface AreaSummary {
  area_id: string;
  name: string;
  well_count: number;
  center_lat?: number;
  center_lon?: number;
}

// Fallback Permian Basin data if backend API is unreachable or offline
const FALLBACK_AREAS: AreaSummary[] = [
  { area_id: 'AREA-01', name: 'Northeast Block 8', well_count: 5, center_lat: 32.4412, center_lon: -102.1124 },
  { area_id: 'AREA-02', name: 'Northeast Block 7', well_count: 4, center_lat: 32.4150, center_lon: -102.0950 },
  { area_id: 'AREA-03', name: 'Southwest Block 24', well_count: 5, center_lat: 32.1892, center_lon: -102.4512 },
  { area_id: 'AREA-04', name: 'Northwest Block 12', well_count: 3, center_lat: 32.5510, center_lon: -102.3200 },
];

const FALLBACK_WELLS: MapWell[] = [
  {
    asset_id: 'WELL-0001',
    name: 'WELL-0001',
    well_type: 'T200',
    area_name: 'Northeast Block 8',
    lat: 32.4412,
    lon: -102.1124,
    recorded_status: 'active',
    wellhead_temp_c: 34.2,
    ambient_temp_c: 31.8,
    delta_temp_c: 2.4,
    is_producing: false,
    has_active_spill: true,
    spill_est_volume_bbl: 4.8,
    latest_notes: 'Valve packing failure during high ambient temp. Containment boom deployed.',
    inspected_at: '2026-08-14'
  },
  {
    asset_id: 'WELL-0002',
    name: 'WELL-0002',
    well_type: 'T200',
    area_name: 'Northeast Block 8',
    lat: 32.4450,
    lon: -102.1180,
    recorded_status: 'active',
    wellhead_temp_c: 54.5,
    ambient_temp_c: 32.0,
    delta_temp_c: 22.5,
    is_producing: true,
    has_active_spill: false
  },
  {
    asset_id: 'WELL-0003',
    name: 'WELL-0003',
    well_type: 'T350',
    area_name: 'Northeast Block 8',
    lat: 32.4498,
    lon: -102.1082,
    recorded_status: 'active',
    wellhead_temp_c: 58.2,
    ambient_temp_c: 31.2,
    delta_temp_c: 27.0,
    is_producing: true,
    has_active_spill: false
  },
  {
    asset_id: 'WELL-0004',
    name: 'WELL-0004',
    well_type: 'T200',
    area_name: 'Northeast Block 8',
    lat: 32.4380,
    lon: -102.1050,
    recorded_status: 'active',
    wellhead_temp_c: 52.0,
    ambient_temp_c: 30.5,
    delta_temp_c: 21.5,
    is_producing: true,
    has_active_spill: false
  },
  {
    asset_id: 'WELL-0005',
    name: 'WELL-0005',
    well_type: 'T350',
    area_name: 'Northeast Block 8',
    lat: 32.4350,
    lon: -102.1220,
    recorded_status: 'down',
    wellhead_temp_c: 33.1,
    ambient_temp_c: 31.0,
    delta_temp_c: 2.1,
    is_producing: false,
    has_active_spill: false
  }
];

export const FleetMapView: React.FC<FleetMapViewProps> = ({ onAskCopilot }) => {
  const [wells, setWells] = useState<MapWell[]>(FALLBACK_WELLS);
  const [areas, setAreas] = useState<AreaSummary[]>(FALLBACK_AREAS);
  const [selectedArea, setSelectedArea] = useState<string>('Northeast Block 8');
  const [searchQuery, setSearchQuery] = useState<string>('');
  
  // Base Layer style: 'satellite' or 'carto'
  const [mapStyle, setMapStyle] = useState<'satellite' | 'carto'>('carto');

  // Filter toggles
  const [showSpillsOnly, setShowSpillsOnly] = useState<boolean>(false);
  const [showProducing, setShowProducing] = useState<boolean>(true);
  const [showIdle, setShowIdle] = useState<boolean>(true);

  // Inspector & Selection
  const [selectedWell, setSelectedWell] = useState<MapWell | null>(FALLBACK_WELLS[0]);
  const [copiedCoords, setCopiedCoords] = useState<boolean>(false);

  // Leaflet map instance and container ref
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const markersLayerRef = useRef<L.LayerGroup | null>(null);

  // 1. Fetch live map data from backend API
  useEffect(() => {
    let isMounted = true;
    const fetchMapData = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/map-data');
        if (res.ok) {
          const data = await res.json();
          if (!isMounted) return;

          if (Array.isArray(data.wells) && data.wells.length > 0) {
            setWells(data.wells);
            // Default selected well to one with an active spill or first well
            const firstSpill = data.wells.find((w: MapWell) => w.has_active_spill);
            setSelectedWell(firstSpill || data.wells[0]);
          }

          if (Array.isArray(data.areas) && data.areas.length > 0) {
            setAreas(data.areas);
          }
        }
      } catch (err) {
        console.warn('Map API unreachable, using resilient offline oilfield dataset:', err);
      }
    };

    fetchMapData();
    return () => { isMounted = false; };
  }, []);

  // Filter wells by selected area, search string, and layer toggles
  const filteredWells = useMemo(() => {
    return wells.filter(w => {
      // Area match
      if (selectedArea !== 'all' && w.area_name !== selectedArea) return false;
      
      // Search match
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase().trim();
        const matchesId = w.asset_id.toLowerCase().includes(query);
        const matchesName = w.name.toLowerCase().includes(query);
        const matchesArea = w.area_name.toLowerCase().includes(query);
        if (!matchesId && !matchesName && !matchesArea) return false;
      }

      // Layer filters
      if (showSpillsOnly && !w.has_active_spill) return false;
      if (!showProducing && w.is_producing) return false;
      if (!showIdle && !w.is_producing) return false;

      return true;
    });
  }, [wells, selectedArea, searchQuery, showSpillsOnly, showProducing, showIdle]);

  // 2. Initialize Leaflet Map
  useEffect(() => {
    if (!mapContainerRef.current) return;
    if (mapInstanceRef.current) return; // already initialized

    // Center on Permian Basin
    const initialLat = 32.4412;
    const initialLon = -102.1124;

    const map = L.map(mapContainerRef.current, {
      center: [initialLat, initialLon],
      zoom: 14,
      zoomControl: false, // We render custom Neubrutalist zoom controls
    });

    // Default tile layer: CartoDB Positron for clean drafting style
    const cartoTileUrl = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';
    const tileLayer = L.tileLayer(cartoTileUrl, {
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(map);

    tileLayerRef.current = tileLayer;

    // Layer group for well markers
    const markersGroup = L.layerGroup().addTo(map);
    markersLayerRef.current = markersGroup;

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // 3. Switch Tile Layer (Satellite vs Carto)
  useEffect(() => {
    if (!mapInstanceRef.current || !tileLayerRef.current) return;

    mapInstanceRef.current.removeLayer(tileLayerRef.current);

    const tileUrl = mapStyle === 'satellite'
      ? 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
      : 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';

    const attribution = mapStyle === 'satellite'
      ? 'Source: Esri, Maxar, Earthstar Geographics'
      : '&copy; OpenStreetMap contributors &copy; CARTO';

    const newTileLayer = L.tileLayer(tileUrl, {
      attribution,
      maxZoom: 18,
      subdomains: mapStyle === 'carto' ? 'abcd' : '',
    }).addTo(mapInstanceRef.current);

    tileLayerRef.current = newTileLayer;
  }, [mapStyle]);

  // 4. Update Markers on Leaflet Map
  useEffect(() => {
    const map = mapInstanceRef.current;
    const markersGroup = markersLayerRef.current;
    if (!map || !markersGroup) return;

    markersGroup.clearLayers();

    if (filteredWells.length === 0) return;

    filteredWells.forEach(well => {
      const isSelected = selectedWell?.asset_id === well.asset_id;
      const hasSpill = well.has_active_spill;
      const isProducing = well.is_producing;

      // Color coding: Red = Active Spill, Green = Producing, Yellow = Idle/Shut-in
      const fillColor = hasSpill ? '#ef4444' : isProducing ? '#22c55e' : '#eab308';
      const radius = hasSpill ? 9 : isSelected ? 8 : 6;
      const weight = isSelected ? 3 : 2;

      // Outer ripple ring for active spills
      if (hasSpill) {
        L.circleMarker([well.lat, well.lon], {
          radius: 18,
          fillColor: '#ef4444',
          fillOpacity: 0.25,
          color: '#ef4444',
          weight: 1.5,
          dashArray: '3,3',
          interactive: false
        }).addTo(markersGroup);
      }

      // Outer focus ring for selected well
      if (isSelected) {
        L.circleMarker([well.lat, well.lon], {
          radius: 14,
          fillColor: 'transparent',
          color: '#000000',
          weight: 2.5,
          dashArray: '4,4',
          interactive: false
        }).addTo(markersGroup);
      }

      // Main Wellhead Circle Marker
      const marker = L.circleMarker([well.lat, well.lon], {
        radius,
        fillColor,
        fillOpacity: 0.95,
        color: '#000000',
        weight,
      });

      // Sleek Neubrutalist Tooltip on Hover (no permanent colliding text!)
      const deltaText = well.delta_temp_c !== null ? `${well.delta_temp_c}°C` : 'N/A';
      const statusBadge = hasSpill 
        ? `<span style="background:#fee2e2;color:#991b1b;padding:2px 6px;border:1px solid #000;font-weight:900;font-size:10px;">⚠️ SPILL: ${well.spill_est_volume_bbl || 0} BBL</span>`
        : isProducing 
          ? `<span style="background:#dcfce7;color:#166534;padding:2px 6px;border:1px solid #000;font-weight:900;font-size:10px;">PRODUCING (ΔT: ${deltaText})</span>`
          : `<span style="background:#fef9c3;color:#854d0e;padding:2px 6px;border:1px solid #000;font-weight:900;font-size:10px;">IDLE / COLD (ΔT: ${deltaText})</span>`;

      const tooltipContent = `
        <div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.4;">
          <div style="font-weight:900;font-size:12px;margin-bottom:3px;">${well.name}</div>
          <div>${statusBadge}</div>
        </div>
      `;

      marker.bindTooltip(tooltipContent, {
        direction: 'top',
        offset: [0, -8],
        opacity: 1,
        className: 'neo-leaflet-tooltip'
      });

      marker.on('click', () => {
        setSelectedWell(well);
      });

      marker.addTo(markersGroup);
    });

  }, [filteredWells, selectedWell]);

  // 5. Fit bounds when Area changes
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || filteredWells.length === 0) return;

    const bounds = L.latLngBounds(filteredWells.map(w => [w.lat, w.lon]));
    map.flyToBounds(bounds, {
      padding: [40, 40],
      maxZoom: 15,
      duration: 1.0
    });
  }, [selectedArea]);

  // Leaflet Zoom Actions
  const handleZoomIn = () => {
    mapInstanceRef.current?.zoomIn();
  };

  const handleZoomOut = () => {
    mapInstanceRef.current?.zoomOut();
  };

  const handleResetView = () => {
    if (!mapInstanceRef.current || filteredWells.length === 0) return;
    const bounds = L.latLngBounds(filteredWells.map(w => [w.lat, w.lon]));
    mapInstanceRef.current.flyToBounds(bounds, { padding: [40, 40], duration: 0.8 });
  };

  const handleCopyGPS = (lat: number, lon: number) => {
    navigator.clipboard.writeText(`${lat.toFixed(6)}, ${lon.toFixed(6)}`);
    setCopiedCoords(true);
    setTimeout(() => setCopiedCoords(false), 2000);
  };

  // Counts for layer badges
  const totalSpillsCount = wells.filter(w => w.has_active_spill).length;
  const totalProducingCount = wells.filter(w => w.is_producing).length;
  const totalIdleCount = wells.filter(w => !w.is_producing).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', paddingBottom: '32px' }}>
      
      {/* 1. Header Toolbar with Area Selector, Search & Filters */}
      <div className="neo-card" style={{ background: '#ffffff', padding: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '14px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div 
                style={{ 
                  background: 'var(--accent-yellow)', 
                  border: '2px solid #000', 
                  padding: '6px', 
                  boxShadow: 'var(--shadow-xs)' 
                }}
              >
                <Navigation size={20} />
              </div>
              <h2 style={{ fontSize: '1.45rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '-0.02em' }}>
                Oilfield Lease & Well Cartography
              </h2>
            </div>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginTop: '4px', fontWeight: 500 }}>
              Live Permian Basin grid: Wellhead GPS, thermal states, and environmental containment.
            </p>
          </div>

          {/* Quick Search & Area Selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            {/* Search Input */}
            <div style={{ position: 'relative', minWidth: '180px' }}>
              <Search size={15} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: '#71717a' }} />
              <input
                type="text"
                placeholder="Find well (e.g. 290)..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="neo-input"
                style={{ 
                  paddingLeft: '32px', 
                  fontSize: '0.82rem', 
                  paddingTop: '6px', 
                  paddingBottom: '6px',
                  fontWeight: 600,
                  width: '100%'
                }}
              />
            </div>

            {/* Area Filter */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Filter size={14} /> Area:
              </span>
              <select
                className="neo-select"
                value={selectedArea}
                onChange={(e) => setSelectedArea(e.target.value)}
                style={{ fontSize: '0.85rem', fontWeight: 700 }}
              >
                <option value="all">All Fleet Areas ({wells.length} Wells)</option>
                {areas.map(a => (
                  <option key={a.area_id} value={a.name}>
                    {a.name} ({a.well_count} wells)
                  </option>
                ))}
              </select>
            </div>

            {/* Ask Oily CTA Button */}
            <button
              className="neo-btn neo-btn-primary"
              style={{ fontSize: '0.8rem', padding: '7px 14px', display: 'flex', alignItems: 'center', gap: '6px' }}
              onClick={() => onAskCopilot(
                `Show on a map every well in ${selectedArea === 'all' ? 'Northeast Block 8' : selectedArea} with a verified spill or abnormal thermal delta in the last 90 days.`
              )}
            >
              Ask Oily to Map Area <ArrowRight size={14} />
            </button>
          </div>
        </div>

        {/* 2. Interactive Cartography Layer Ribbon */}
        <div 
          style={{ 
            display: 'flex', 
            gap: '12px', 
            marginTop: '14px', 
            paddingTop: '12px', 
            borderTop: '2px dashed #e4e4e7', 
            flexWrap: 'wrap', 
            alignItems: 'center',
            justifyContent: 'space-between'
          }}
        >
          <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', alignItems: 'center' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 900, textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Layers size={14} /> Display Layers:
            </span>

            {/* Spills Filter */}
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', fontWeight: 700, cursor: 'pointer' }}>
              <input 
                type="checkbox" 
                checked={showSpillsOnly} 
                onChange={(e) => setShowSpillsOnly(e.target.checked)} 
              />
              <span 
                className="neo-badge badge-red" 
                style={{ 
                  fontSize: '0.68rem', 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '4px',
                  background: showSpillsOnly ? 'var(--accent-red)' : '#fee2e2',
                  color: showSpillsOnly ? '#ffffff' : '#991b1b',
                }}
              >
                <AlertTriangle size={12} /> ACTIVE SPILLS ({totalSpillsCount})
              </span>
            </label>

            {/* Producing Wells Filter */}
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', fontWeight: 700, cursor: 'pointer' }}>
              <input 
                type="checkbox" 
                checked={showProducing} 
                onChange={(e) => setShowProducing(e.target.checked)} 
              />
              <span className="neo-badge badge-green" style={{ fontSize: '0.68rem', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Fuel size={12} /> PRODUCING ({totalProducingCount})
              </span>
            </label>

            {/* Idle Wells Filter */}
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', fontWeight: 700, cursor: 'pointer' }}>
              <input 
                type="checkbox" 
                checked={showIdle} 
                onChange={(e) => setShowIdle(e.target.checked)} 
              />
              <span className="neo-badge badge-yellow" style={{ fontSize: '0.68rem', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Radio size={12} /> IDLE / SHUT-IN ({totalIdleCount})
              </span>
            </label>
          </div>

          {/* Map Base Layer Switcher */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              onClick={() => setMapStyle('carto')}
              className="neo-btn"
              style={{ 
                padding: '4px 10px', 
                fontSize: '0.75rem', 
                fontWeight: 800,
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                background: mapStyle === 'carto' ? 'var(--accent-yellow)' : '#ffffff'
              }}
            >
              <MapIcon size={13} /> DRAFTING MAP
            </button>
            <button
              onClick={() => setMapStyle('satellite')}
              className="neo-btn"
              style={{ 
                padding: '4px 10px', 
                fontSize: '0.75rem', 
                fontWeight: 800,
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                background: mapStyle === 'satellite' ? 'var(--accent-yellow)' : '#ffffff'
              }}
            >
              <Satellite size={13} /> SATELLITE
            </button>

            <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', marginLeft: '6px' }}>
              Showing {filteredWells.length} wells
            </span>
          </div>
        </div>
      </div>

      {/* 3. Main Workspace: Interactive Leaflet Map + Right Site Inspector */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: '16px' }}>
        
        {/* Leaflet Map Container */}
        <div 
          className="neo-card" 
          style={{ 
            background: '#ffffff', 
            padding: '10px', 
            position: 'relative', 
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column'
          }}
        >
          {/* Top Overlays: Sector Badge & Compass */}
          <div style={{ position: 'absolute', top: '22px', left: '22px', zIndex: 1000, display: 'flex', gap: '8px' }}>
            <div 
              className="neo-border"
              style={{ 
                background: '#ffffff', 
                padding: '6px 12px', 
                boxShadow: 'var(--shadow-xs)',
                fontWeight: 900,
                fontSize: '0.8rem',
                textTransform: 'uppercase',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
            >
              <Crosshair size={14} color="#000" />
              {selectedArea === 'all' ? 'PERMIAN BASIN - ALL SECTORS' : selectedArea}
            </div>

            <div 
              className="neo-badge badge-dark mono" 
              style={{ padding: '6px 10px', fontSize: '0.72rem' }}
            >
              {filteredWells.length} ACTIVE WELLPADS
            </div>
          </div>

          {/* Compass Rose */}
          <div 
            className="neo-border"
            style={{ 
              position: 'absolute', 
              top: '22px', 
              right: '22px', 
              background: '#ffffff', 
              padding: '6px 12px', 
              boxShadow: 'var(--shadow-xs)',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontWeight: 800,
              fontSize: '0.75rem',
              zIndex: 1000
            }}
          >
            <Compass size={16} /> NORTH ↑
          </div>

          {/* Floating Zoom Controls */}
          <div 
            style={{ 
              position: 'absolute', 
              bottom: '22px', 
              right: '22px', 
              zIndex: 1000, 
              display: 'flex', 
              flexDirection: 'column', 
              gap: '6px' 
            }}
          >
            <button
              onClick={handleZoomIn}
              className="neo-btn"
              style={{ width: '36px', height: '36px', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              title="Zoom In"
            >
              <ZoomIn size={18} />
            </button>
            <button
              onClick={handleZoomOut}
              className="neo-btn"
              style={{ width: '36px', height: '36px', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              title="Zoom Out"
            >
              <ZoomOut size={18} />
            </button>
            <button
              onClick={handleResetView}
              className="neo-btn"
              style={{ width: '36px', height: '36px', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              title="Reset View"
            >
              <RotateCcw size={16} />
            </button>
          </div>

          {/* Scale / Coordinate System Badge */}
          <div 
            className="neo-border"
            style={{ 
              position: 'absolute', 
              bottom: '22px', 
              left: '22px', 
              zIndex: 1000,
              background: '#ffffff',
              padding: '6px 12px',
              boxShadow: 'var(--shadow-xs)',
              display: 'flex',
              alignItems: 'center',
              gap: '12px'
            }}
          >
            <div>
              <div style={{ fontSize: '0.65rem', fontWeight: 800, color: '#71717a' }}>COORDINATE SYSTEM</div>
              <div className="mono" style={{ fontSize: '0.72rem', fontWeight: 800, marginTop: '2px' }}>
                WGS84 • EPSG:4326
              </div>
            </div>
            <div style={{ borderLeft: '1.5px solid #e4e4e7', paddingLeft: '10px' }}>
              <div style={{ fontSize: '0.65rem', fontWeight: 800, color: '#71717a' }}>INTERACTION</div>
              <div style={{ fontSize: '0.72rem', fontWeight: 700 }}>Click wellhead to inspect</div>
            </div>
          </div>

          {/* Leaflet Map Div */}
          <div 
            ref={mapContainerRef}
            style={{ 
              width: '100%', 
              height: '560px', 
              background: '#fbfbf7', 
              border: '2.5px solid var(--border-color)',
              boxShadow: 'var(--shadow-sm)'
            }}
          />

          {/* Bottom Cartography Legend Bar */}
          <div 
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'space-between', 
              flexWrap: 'wrap', 
              gap: '12px', 
              marginTop: '10px', 
              padding: '8px 12px', 
              background: '#f4f4f5', 
              border: '1.5px solid var(--border-color)',
              fontSize: '0.75rem',
              fontWeight: 700
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
              <span style={{ fontWeight: 900, textTransform: 'uppercase' }}>LEGEND:</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#22c55e', border: '1.5px solid #000' }} />
                <span>Producing (ΔT ≥ 15°C)</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#eab308', border: '1.5px solid #000' }} />
                <span>Idle / Cold (ΔT &lt; 15°C)</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <div style={{ width: '14px', height: '14px', borderRadius: '50%', background: '#ef4444', border: '1.5px solid #000' }} />
                <span>Active Spill Alert ({totalSpillsCount} Total)</span>
              </div>
            </div>

            <span style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>
              Hover wellhead for quick stats • Click to load site inspector
            </span>
          </div>
        </div>

        {/* 4. Right Operator Inspection Drawer */}
        <div 
          className="neo-card" 
          style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            gap: '14px',
            background: '#ffffff',
            height: 'fit-content'
          }}
        >
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '2.5px solid var(--border-color)', paddingBottom: '10px' }}>
            <div>
              <span style={{ fontSize: '0.72rem', fontWeight: 900, textTransform: 'uppercase', color: 'var(--text-muted)', letterSpacing: '0.04em' }}>
                SITE TELEMETRY INSPECTOR
              </span>
              <h3 style={{ fontSize: '1.3rem', fontWeight: 900, marginTop: '2px' }}>
                {selectedWell ? selectedWell.name : 'Select Wellpad'}
              </h3>
            </div>

            {selectedWell && (
              <span 
                className={`neo-badge ${selectedWell.has_active_spill ? 'badge-red' : selectedWell.is_producing ? 'badge-green' : 'badge-yellow'}`}
                style={{ fontSize: '0.7rem' }}
              >
                {selectedWell.has_active_spill ? 'SPILL ALERT' : selectedWell.is_producing ? 'PRODUCING' : 'IDLE / SHUT-IN'}
              </span>
            )}
          </div>

          {selectedWell ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              
              {/* Location & Sector Card */}
              <div style={{ background: 'var(--bg-muted)', padding: '12px', border: '2px solid var(--border-color)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontSize: '0.7rem', fontWeight: 800, color: 'var(--text-muted)' }}>SECTOR & ASSET ID</div>
                  <span className="neo-badge badge-dark mono" style={{ fontSize: '0.65rem' }}>{selectedWell.well_type}</span>
                </div>
                <div style={{ fontWeight: 800, fontSize: '0.95rem', marginTop: '2px' }}>
                  📍 {selectedWell.area_name}
                </div>

                {/* GPS Coordinates with Copy Button */}
                <div style={{ marginTop: '10px', paddingTop: '8px', borderTop: '1px solid #d4d4d8', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: '0.65rem', fontWeight: 700, color: '#71717a' }}>GPS COORDINATES</div>
                    <div className="mono" style={{ fontWeight: 800, fontSize: '0.82rem' }}>
                      {selectedWell.lat.toFixed(6)}° N, {selectedWell.lon.toFixed(6)}° W
                    </div>
                  </div>
                  <button
                    onClick={() => handleCopyGPS(selectedWell.lat, selectedWell.lon)}
                    className="neo-btn"
                    style={{ padding: '4px 8px', fontSize: '0.7rem', display: 'flex', alignItems: 'center', gap: '4px' }}
                    title="Copy coordinates"
                  >
                    {copiedCoords ? <Check size={12} color="#16a34a" /> : <Copy size={12} />}
                    {copiedCoords ? 'Copied!' : 'Copy'}
                  </button>
                </div>
              </div>

              {/* Thermal Telemetry & Producing State */}
              <div style={{ border: '2px solid var(--border-color)', padding: '12px', background: '#ffffff' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 900, textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Flame size={14} color="#f97316" /> Thermal Telemetry
                  </span>
                  <span 
                    className="mono" 
                    style={{ 
                      fontSize: '0.72rem', 
                      fontWeight: 800, 
                      color: (selectedWell.delta_temp_c || 0) >= 15 ? '#15803d' : '#b45309' 
                    }}
                  >
                    {(selectedWell.delta_temp_c || 0) >= 15 ? 'NOMINAL FLOW' : 'COLD HEAD'}
                  </span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '10px' }}>
                  <div style={{ background: '#f4f4f5', padding: '8px', border: '1.5px solid #000' }}>
                    <div style={{ fontSize: '0.65rem', fontWeight: 700, color: '#71717a' }}>WELLHEAD TEMP</div>
                    <div className="mono" style={{ fontSize: '1.05rem', fontWeight: 900 }}>
                      {selectedWell.wellhead_temp_c !== null ? `${selectedWell.wellhead_temp_c.toFixed(1)}°C` : 'N/A'}
                    </div>
                  </div>

                  <div style={{ background: '#f4f4f5', padding: '8px', border: '1.5px solid #000' }}>
                    <div style={{ fontSize: '0.65rem', fontWeight: 700, color: '#71717a' }}>AMBIENT TEMP</div>
                    <div className="mono" style={{ fontSize: '1.05rem', fontWeight: 900 }}>
                      {selectedWell.ambient_temp_c !== null ? `${selectedWell.ambient_temp_c.toFixed(1)}°C` : 'N/A'}
                    </div>
                  </div>
                </div>

                {/* Thermal Delta Bar Gauge */}
                <div style={{ marginTop: '10px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', fontWeight: 800 }}>
                    <span>THERMAL DELTA (ΔT):</span>
                    <span className="mono" style={{ fontSize: '0.85rem' }}>
                      {selectedWell.delta_temp_c !== null ? `${selectedWell.delta_temp_c.toFixed(1)}°C` : 'N/A'}
                    </span>
                  </div>
                  <div style={{ width: '100%', height: '8px', background: '#e4e4e7', border: '1.5px solid #000', marginTop: '4px', position: 'relative' }}>
                    <div 
                      style={{ 
                        height: '100%', 
                        width: `${Math.min(Math.max(((selectedWell.delta_temp_c || 0) / 40) * 100, 4), 100)}%`,
                        background: (selectedWell.delta_temp_c || 0) >= 15 ? 'var(--accent-green)' : 'var(--accent-yellow)',
                        transition: 'width 0.3s ease'
                      }} 
                    />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.62rem', color: '#71717a', marginTop: '2px' }}>
                    <span>0°C (Cold)</span>
                    <span style={{ fontWeight: 700 }}>15°C Producing Limit</span>
                    <span>40°C+</span>
                  </div>
                </div>
              </div>

              {/* Spill Incident Log (If Present) */}
              {selectedWell.has_active_spill ? (
                <div style={{ background: 'var(--accent-red-light)', padding: '12px', border: '2px solid var(--border-color)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ fontSize: '0.72rem', fontWeight: 900, color: '#991b1b', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <AlertTriangle size={14} /> ACTIVE SPILL REPORT
                    </div>
                    {selectedWell.inspected_at && (
                      <span className="mono" style={{ fontSize: '0.68rem', fontWeight: 800, color: '#7f1d1d' }}>
                        {selectedWell.inspected_at.slice(0, 10)}
                      </span>
                    )}
                  </div>

                  <div className="mono" style={{ fontWeight: 900, fontSize: '1.35rem', color: '#7f1d1d', marginTop: '4px' }}>
                    {selectedWell.spill_est_volume_bbl !== null ? `${selectedWell.spill_est_volume_bbl} BBL` : 'UNQUANTIFIED'}
                  </div>

                  <div style={{ fontSize: '0.78rem', lineHeight: '1.4', marginTop: '6px', color: '#3f3f46', background: '#ffffff', padding: '8px', border: '1.5px solid #000' }}>
                    <strong>Inspection Notes:</strong>
                    <p style={{ marginTop: '3px' }}>{selectedWell.latest_notes || 'Surface oil seepage noted during latest site inspection.'}</p>
                  </div>
                </div>
              ) : (
                <div style={{ background: '#f0fdf4', padding: '10px 12px', border: '2px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <CheckCircle2 size={16} color="#16a34a" />
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#166534' }}>
                    Containment Clear: No active spills reported on this wellpad.
                  </span>
                </div>
              )}

              {/* Action Buttons */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '4px' }}>
                <button
                  className="neo-btn neo-btn-primary"
                  style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}
                  onClick={() => onAskCopilot(
                    `Provide a complete operational diagnosis, telemetry analysis, and incident check for ${selectedWell.asset_id} in ${selectedWell.area_name}.`
                  )}
                >
                  Ask Oily About {selectedWell.name} <ArrowRight size={14} />
                </button>

                <button
                  className="neo-btn"
                  style={{ width: '100%', fontSize: '0.8rem', background: '#ffffff' }}
                  onClick={() => onAskCopilot(
                    `Check work order and maintenance records for ${selectedWell.asset_id}. Has this well had repeated packing or casing failures?`
                  )}
                >
                  Check Maintenance Records
                </button>
              </div>

            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '40px 14px', color: 'var(--text-muted)' }}>
              <MapPin size={36} style={{ margin: '0 auto 10px auto', opacity: 0.4 }} />
              <p style={{ fontWeight: 700 }}>Click on any wellhead marker on the map to inspect telemetry.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
