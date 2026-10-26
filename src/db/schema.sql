-- Asset Intelligence Copilot: Core Database Schema
-- Supports relational time-series, unstructured reports, pgvector embeddings, and shared context

CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Fleet Teams & Users
CREATE TABLE IF NOT EXISTS fleet_teams (
    team_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    lead_user_id VARCHAR(32) NOT NULL
);

CREATE TABLE IF NOT EXISTS fleet_users (
    user_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    role VARCHAR(64) NOT NULL,
    team_id VARCHAR(32) REFERENCES fleet_teams(team_id)
);

-- 2. Fleet Areas
CREATE TABLE IF NOT EXISTS fleet_areas (
    area_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    team_id VARCHAR(32) REFERENCES fleet_teams(team_id),
    center_lat DOUBLE PRECISION NOT NULL,
    center_lon DOUBLE PRECISION NOT NULL
);

-- 3. Well Type Rules (Ingested dynamically from manuals)
CREATE TABLE IF NOT EXISTS well_type_rules (
    well_type VARCHAR(16) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    min_producing_temp_delta_c REAL NOT NULL, -- 15.0 for T200, 20.0 for T350
    temp_alarm_threshold_c REAL NOT NULL,     -- 85.0 for T200, 95.0 for T350
    default_rca_repairs_threshold INT DEFAULT 3,
    manual_doc_path VARCHAR(256)
);

-- 4. Wells Metadata
CREATE TABLE IF NOT EXISTS wells (
    asset_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    asset_category VARCHAR(64) DEFAULT 'oil_well',
    well_type VARCHAR(16) REFERENCES well_type_rules(well_type),
    area_id VARCHAR(32) REFERENCES fleet_areas(area_id),
    team_id VARCHAR(32) REFERENCES fleet_teams(team_id),
    in_charge_user_id VARCHAR(32) REFERENCES fleet_users(user_id),
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    installed_on DATE NOT NULL,
    recorded_status VARCHAR(32) NOT NULL, -- 'active', 'down', or 'plugged'
    type_history JSONB,
    team_history JSONB,
    status VARCHAR(64),
    decommissioned_on DATE
);
ALTER TABLE wells ADD COLUMN IF NOT EXISTS type_history JSONB;
ALTER TABLE wells ADD COLUMN IF NOT EXISTS team_history JSONB;
ALTER TABLE wells ADD COLUMN IF NOT EXISTS status VARCHAR(64);
ALTER TABLE wells ADD COLUMN IF NOT EXISTS decommissioned_on DATE;
CREATE INDEX IF NOT EXISTS idx_wells_area ON wells(area_id);
CREATE INDEX IF NOT EXISTS idx_wells_type ON wells(well_type);
CREATE INDEX IF NOT EXISTS idx_wells_status ON wells(status);

-- 5. Equipment Inventory
CREATE TABLE IF NOT EXISTS equipment (
    equipment_id VARCHAR(64) PRIMARY KEY,
    asset_id VARCHAR(32) REFERENCES wells(asset_id),
    kind VARCHAR(64) NOT NULL, -- 'wellhead', 'pump_jack', 'rod_string', etc.
    model VARCHAR(128) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_equipment_asset ON equipment(asset_id);

-- 6. Weekly Inspections (Ground Truth)
CREATE TABLE IF NOT EXISTS inspections (
    inspection_id VARCHAR(64) PRIMARY KEY,
    asset_id VARCHAR(32) REFERENCES wells(asset_id),
    inspected_at TIMESTAMPTZ NOT NULL,
    inspector_user_id VARCHAR(32) REFERENCES fleet_users(user_id),
    method VARCHAR(16) NOT NULL, -- 'drone' or 'manual'
    ambient_temp_c REAL NOT NULL,
    wellhead_temp_c REAL NOT NULL,
    delta_temp_c REAL NOT NULL,  -- computed as wellhead_temp_c - ambient_temp_c
    is_producing BOOLEAN NOT NULL,
    spill_detected BOOLEAN DEFAULT FALSE,
    spill_area_pct REAL,
    spill_est_volume_bbl REAL,
    notes TEXT,
    is_false_positive_spill BOOLEAN DEFAULT FALSE,
    recorded_at TIMESTAMPTZ
);
ALTER TABLE inspections ADD COLUMN IF NOT EXISTS recorded_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_inspections_asset_date ON inspections(asset_id, inspected_at DESC);
CREATE INDEX IF NOT EXISTS idx_inspections_date ON inspections(inspected_at);
CREATE INDEX IF NOT EXISTS idx_inspections_spill ON inspections(spill_detected, is_false_positive_spill);

-- 7. Maintenance Records
CREATE TABLE IF NOT EXISTS maintenance (
    maintenance_id VARCHAR(64) PRIMARY KEY,
    asset_id VARCHAR(32) REFERENCES wells(asset_id),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    maintenance_type VARCHAR(32) NOT NULL, -- 'scheduled' or 'corrective'
    equipment_kind VARCHAR(64) NOT NULL,
    issue TEXT NOT NULL,
    action_taken TEXT NOT NULL,
    technician_user_id VARCHAR(32),
    contractor VARCHAR(128),
    downtime_hours REAL,
    cost_labor REAL DEFAULT 0,
    cost_parts REAL DEFAULT 0,
    cost_total REAL DEFAULT 0,
    triggered_by_inspection_id VARCHAR(64),
    report_file VARCHAR(256),
    recorded_at TIMESTAMPTZ,
    cost_revision JSONB
);
ALTER TABLE maintenance ADD COLUMN IF NOT EXISTS recorded_at TIMESTAMPTZ;
ALTER TABLE maintenance ADD COLUMN IF NOT EXISTS cost_revision JSONB;
CREATE INDEX IF NOT EXISTS idx_maintenance_asset_started ON maintenance(asset_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_maintenance_equipment ON maintenance(asset_id, equipment_kind, maintenance_type);

-- 8. Structured Maintenance Report Metrics (Bridge from Unstructured to Structured)
CREATE TABLE IF NOT EXISTS maintenance_report_metrics (
    report_file VARCHAR(256) PRIMARY KEY,
    maintenance_id VARCHAR(64) REFERENCES maintenance(maintenance_id),
    asset_id VARCHAR(32) REFERENCES wells(asset_id),
    triggered_by_inspection_id VARCHAR(64),
    hours_to_contain REAL,               -- e.g. 7.0 (parsed from report)
    hours_to_report REAL,                -- e.g. 41.0
    sr01_status VARCHAR(32),             -- 'met', 'not_met'
    sr02_status VARCHAR(32),             -- 'met', 'not_met'
    sr03_status VARCHAR(32),             -- 'met', 'not_met', 'in_progress'
    ws05_tested_psi REAL,
    highest_tph_pct REAL,
    total_cost_usd REAL,
    summary_fix TEXT,
    parts_installed JSONB,
    follow_up JSONB
);
ALTER TABLE maintenance_report_metrics ADD COLUMN IF NOT EXISTS parts_installed JSONB;
ALTER TABLE maintenance_report_metrics ADD COLUMN IF NOT EXISTS follow_up JSONB;
CREATE INDEX IF NOT EXISTS idx_report_metrics_asset ON maintenance_report_metrics(asset_id);

-- 9. Regulatory Events
CREATE TABLE IF NOT EXISTS regulatory_events (
    event_id VARCHAR(64) PRIMARY KEY,
    asset_id VARCHAR(32) REFERENCES wells(asset_id),
    date DATE NOT NULL,
    agency VARCHAR(128) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    protocol_id VARCHAR(32),
    related_inspection_id VARCHAR(64),
    hours_to_report REAL,
    fine_usd REAL DEFAULT 0,
    status VARCHAR(32) NOT NULL, -- 'open' or 'closed'
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_reg_asset_date ON regulatory_events(asset_id, date DESC);

-- 10. Document Sections (Reports, Manuals & SOPs Hybrid Vector Store)
CREATE TABLE IF NOT EXISTS document_sections (
    section_id SERIAL PRIMARY KEY,
    doc_type VARCHAR(32) NOT NULL, -- 'maintenance_report', 'manual', 'sop'
    doc_path VARCHAR(256) NOT NULL,
    asset_id VARCHAR(32),
    section_title VARCHAR(128),
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(384) -- BAAI/bge-small-en-v1.5
);
CREATE INDEX IF NOT EXISTS idx_doc_asset ON document_sections(asset_id);
CREATE INDEX IF NOT EXISTS idx_doc_type ON document_sections(doc_type);

-- 11. Shared Context, Overrides & Dynamic Policies
CREATE TABLE IF NOT EXISTS shared_context (
    override_id SERIAL PRIMARY KEY,
    note_id VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    author_user_id VARCHAR(32) REFERENCES fleet_users(user_id),
    scope VARCHAR(32) NOT NULL, -- 'inspection', 'asset', 'well_type', 'fleet'
    target_id VARCHAR(64) NOT NULL,
    note_type VARCHAR(32) NOT NULL, -- 'correction', 'operator_note', 'operator_feedback', 'policy_rule'
    original_value JSONB,
    corrected_value JSONB,
    text TEXT,
    valid_from DATE,
    valid_to DATE,
    is_confirmed BOOLEAN DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_shared_context_target ON shared_context(target_id);

-- 12. User Session Turns (Private Conversational Memory)
-- Persists discussed entities per user so "the wells we discussed yesterday" works
-- across server restarts, workers, and new chat sessions.
CREATE TABLE IF NOT EXISTS session_turns (
    turn_id SERIAL PRIMARY KEY,
    user_id VARCHAR(32) NOT NULL,
    session_id VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    user_query TEXT NOT NULL,
    narrative_response TEXT NOT NULL,
    discussed_assets TEXT[] DEFAULT '{}',
    citations JSONB DEFAULT '[]'::jsonb,
    generative_ui JSONB
);
CREATE INDEX IF NOT EXISTS idx_session_turns_user ON session_turns(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_turns_session ON session_turns(user_id, session_id, created_at DESC);
