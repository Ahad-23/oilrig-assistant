# Asset Intelligence Copilot: Architecture & System Design Single Source of Truth (SSOT)

> **Document Version:** 1.0.0  
> **Challenge:** FlytBase Local Challenge · Hacktoberfest 2026 Hack Day  
> **Status:** Architecture & Implementation Design Locked (No application code written yet)  
> **Target LLM:** Google Gemma 4 (`gemma-4-26b-a4b-it` & `gemma-4-31b-it`) hosted on Google AI Studio with OpenRouter fallback  
> **Stack Core:** Python 3.11+, `uv`, PostgreSQL 16 + `pgvector`, LangGraph, LiteLLM, DeepEval + Pytest, React + OpenUI  

---

## 1. Problem Statement & Domain Understanding

### 1.1 The Operational Problem
In onshore oilfield operations, hundreds of rod-lift wells produce crude oil across wide geographical blocks. Operations generate massive, heterogeneous, multi-modal data streams:
- Weekly visual and thermal drone/manual inspection logs (~40,000 records).
- Scheduled and corrective maintenance records (~5,700 events).
- Free-text corrective repair reports (~1,500 Markdown reports containing root causes, containment times, and soil test results).
- Regulatory event filings, notices of violation (NOVs), and environmental fines.
- Human operator feedback notes, field observations, and shut-in plans.
- Formal operating manuals ([T200.md](file:///c:/Users/Ahad/Documents/repos/asset-copilot/dataset-problem_statement/sample-data/fleet/well-types/T200.md), [T350.md](file:///c:/Users/Ahad/Documents/repos/asset-copilot/dataset-problem_statement/sample-data/fleet/well-types/T350.md)) and safety standard operating procedures ([spill-response-sop.md](file:///c:/Users/Ahad/Documents/repos/asset-copilot/dataset-problem_statement/sample-data/fleet/sops/spill-response-sop.md), [regulatory-compliance-sop.md](file:///c:/Users/Ahad/Documents/repos/asset-copilot/dataset-problem_statement/sample-data/fleet/sops/regulatory-compliance-sop.md), [field-work-sop.md](file:///c:/Users/Ahad/Documents/repos/asset-copilot/dataset-problem_statement/sample-data/fleet/sops/field-work-sop.md)).

Today, querying critical operational facts (e.g., *"Which wells in my area were down longest this summer, and why?"* or *"Did any spill exceed regulatory reporting deadlines?"*) requires manually collating data across disparate systems, reading PDF/Markdown reports, and applying complex manual cross-references.

### 1.2 Core Domain Rules & Calculation Logic

| Domain Concept | Operational Rule & Governing Document | Implementation Ground Truth |
| :--- | :--- | :--- |
| **Is the well producing oil?** | Fluid from reservoir is warmer than air. A stopped wellhead cools to ambient. Absolute temp does **not** matter (e.g. idle wellhead can hit 50°C on hot summer days). | **T200 Wells:** $\Delta T = T_{wellhead} - T_{ambient} \ge 15.0^\circ\text{C}$<br>**T350 Wells:** $\Delta T = T_{wellhead} - T_{ambient} \ge 20.0^\circ\text{C}$ |
| **Operational Downtime** | Measured in units of weekly inspections. Missed inspections add 0 downtime. | **Each non-producing weekly inspection = 7 days downtime.** (Do not use `maintenance.downtime_hours`, which measures repair job duration). |
| **Status Stale Data** | `metadata.json` records `recorded_status` (`active`/`down`), but is refreshed only monthly. | **Weekly inspection thermal $\Delta T$ is the ground truth.** When they disagree, flag `recorded_status` as stale/out-of-date. |
| **Spill Classification & Deadlines** | Governed by Spill Response SOP (`SOP-SR`). Discovery time = Inspection timestamp. | - **Minor (< 1 bbl):** Clean up, no agency filing.<br>- **Moderate (1 to < 5 bbl):** Clean up, notify HSE in 72h.<br>- **Reportable (5 to < 25 bbl):** Written report to State Commission within **24 hours** (SR-01); source contained within **4 hours** (SR-02); remediated to $\le 1.0\%$ TPH verified within **60 days** (SR-03).<br>- **Major ($\ge 25$ bbl):** Notice in **2 hours**.<br>- **Pad Area Shut-in:** Spills covering $> 5\%$ pad area require immediate well shut-in. |
| **Root-Cause Analysis (RCA)** | Governed by Well Manuals Section 10. | $\ge 3$ corrective repairs on the same equipment kind within 12 months require an RCA before closing repair. Can be dynamically overridden (e.g. 2 repairs for T350). |
| **Human Notes & Overrides** | `context.jsonl` entries. | - `note_type: "correction"` targeting `inspection_id` overrides raw data (e.g. rainwater false positive, re-measured temp).<br>- `operator_note` / `operator_feedback` provide supplemental operational context (e.g. planned workovers). |
| **Conflict Handling** | Human statements vs. hard sensor logs or disagreements between users. | **Never silently pick a side.** Output both claims, highlight discrepancies, mark unconfirmed claims, and request confirmation. |

---

## 2. Decision Log & Architectural Trade-offs ("Why This?")

### 2.1 Storage Architecture: Why PostgreSQL + pgvector?
* **Why NOT Pure RAG / Vector Search?**
  - Computing downtime sums over 40,000 inspections or generating a 2026 spill heatmap across 200 wells requires exact arithmetic and aggregations (`GROUP BY`, `SUM`, `COUNT`).
  - LLMs reading top-$k$ vector chunks inevitably hallucinate numbers, drop rows, or breach context windows.
  - SQL handles quantitative queries deterministically in $< 5\text{ms}$.
* **Why NOT NoSQL (e.g., MongoDB)?**
  - The oilfield dataset is relational (`Areas` $\to$ `Teams` $\to$ `Wells` $\to$ `Inspections` $\to$ `Repairs` $\to$ `Regulatory Events`).
  - Overriding false-positive spills requires relational joins (`LEFT JOIN context_overrides ON ...`).
* **Why PostgreSQL + pgvector over Dual Stores (SQLite + Chroma)?**
  - Single open-source engine containerized via Docker.
  - Enables **Hybrid Filtering**: Querying metadata with vector similarity in a single query:
    ```sql
    SELECT content, metadata FROM document_sections
    WHERE asset_id = 'WELL-0001' AND doc_type = 'maintenance_report'
    ORDER BY embedding <=> query_embedding LIMIT 3;
    ```
  - Fast batch loading (`COPY`) ensures the 2-hour final test dataset can be ingested in under 5 seconds.

### 2.2 Agent Orchestration: Why LangGraph StateGraph?
* **Why NOT Standard LangChain Chains?**
  - Standard chains are linear and rigid.
  - LangGraph provides a cyclical State Machine DAG:
    $$\text{User Query} \to \text{Router} \to \text{SQL / Hybrid Search} \to \text{Conflict Detector} \to \text{Clarification / Synthesizer}$$
* **Two-Level Memory Isolation**:
  - **Shared Fleet Memory**: Stored in PostgreSQL (`shared_context`). Available across all users.
  - **Private User Memory**: Managed via LangGraph's native session checkpointer (`PostgresSaver`), partitioned strictly by `user_id`. Prevents User A (Jessica Reed) from accessing User B's (Michael Turner) conversational state.

### 2.3 Model Gateway: Why LiteLLM + Google AI Studio Gemma 4?
* **100% Open Weights & Zero Local Disk Footprint**:
  - Hosted directly on **Google AI Studio** using Gemma 4 (`gemma-4-26b-a4b-it` for fast SQL routing, `gemma-4-31b-it` for complex reasoning).
  - Uses free cloud API access with standard API key.
  - Automated cloud-to-cloud failover to OpenRouter's free endpoint (`google/gemma-4-31b-it:free`) via LiteLLM if rate limits occur.

### 2.4 Generative UI: Why OpenUI + React?
* Pre-built registered components for the 6 core visual types required by the challenge:
  1. `StatusCard`: Single well operational health.
  2. `DataTable`: Multi-row listings of wells, repairs, or breaches.
  3. `MetricLineChart`: 13-week temperature trends over time.
  4. `ComparisonBarChart`: Ranked downtime or repair costs.
  5. `WellMap`: Geospatial Leaflet map with coordinates and spill pins.
  6. `SpillHeatmap`: 2D Matrix of Geographic Area $\times$ Month.
* OpenUI provides dynamic generation fallback when the user requests unique or novel ad-hoc visual representations.

### 2.5 Evaluations: Why DeepEval + Pytest?
* **Deterministic Ground-Truth Assertions (Pytest)**:
  - Exact numerical verification for benchmark questions Q1–Q8 (downtime days, spill volumes, counts).
* **Qualitative G-Eval Metrics (DeepEval)**:
  - Evaluates subjective and safety constraints:
    - `ConflictDetectionMetric`: Verifies assistant flags discrepancies without taking sides.
    - `NegativeConstraintMetric`: Verifies assistant states "No recorded reason" rather than hallucinating causes.
    - `CitationGroundingMetric`: Verifies presence of record IDs and SOP protocol codes.

---

## 3. PostgreSQL Database Schema (DDL)

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Fleet Areas
CREATE TABLE fleet_areas (
    area_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    team_id VARCHAR(32) NOT NULL,
    center_lat DOUBLE PRECISION NOT NULL,
    center_lon DOUBLE PRECISION NOT NULL
);

-- 2. Fleet Teams & Users
CREATE TABLE fleet_teams (
    team_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    lead_user_id VARCHAR(32) NOT NULL
);

CREATE TABLE fleet_users (
    user_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    role VARCHAR(64) NOT NULL,
    team_id VARCHAR(32) REFERENCES fleet_teams(team_id)
);

-- 3. Wells Metadata
CREATE TABLE wells (
    asset_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    asset_category VARCHAR(64) DEFAULT 'oil_well',
    well_type VARCHAR(16) NOT NULL, -- 'T200' or 'T350'
    area_id VARCHAR(32) REFERENCES fleet_areas(area_id),
    team_id VARCHAR(32) REFERENCES fleet_teams(team_id),
    in_charge_user_id VARCHAR(32) REFERENCES fleet_users(user_id),
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    installed_on DATE NOT NULL,
    recorded_status VARCHAR(32) NOT NULL -- 'active' or 'down' (stale)
);

-- 4. Equipment Inventory
CREATE TABLE equipment (
    equipment_id VARCHAR(64) PRIMARY KEY,
    asset_id VARCHAR(32) REFERENCES wells(asset_id),
    kind VARCHAR(64) NOT NULL, -- 'wellhead', 'pump_jack', 'rod_string', etc.
    model VARCHAR(128) NOT NULL
);

-- 5. Weekly Inspections (Ground Truth)
CREATE TABLE inspections (
    inspection_id VARCHAR(64) PRIMARY KEY,
    asset_id VARCHAR(32) REFERENCES wells(asset_id),
    inspected_at TIMESTAMPTZ NOT NULL,
    inspector_user_id VARCHAR(32) REFERENCES fleet_users(user_id),
    method VARCHAR(16) NOT NULL, -- 'drone' or 'manual'
    ambient_temp_c REAL NOT NULL,
    wellhead_temp_c REAL NOT NULL,
    delta_temp_c REAL GENERATED ALWAYS AS (wellhead_temp_c - ambient_temp_c) STORED,
    spill_detected BOOLEAN DEFAULT FALSE,
    spill_area_pct REAL,
    spill_est_volume_bbl REAL,
    notes TEXT,
    is_producing BOOLEAN NOT NULL,
    is_false_positive_spill BOOLEAN DEFAULT FALSE
);
CREATE INDEX idx_inspections_asset_date ON inspections (asset_id, inspected_at);

-- 6. Maintenance Events
CREATE TABLE maintenance (
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
    report_file VARCHAR(256)
);
CREATE INDEX idx_maintenance_asset_date ON maintenance (asset_id, started_at);

-- 7. Regulatory Events
CREATE TABLE regulatory_events (
    event_id VARCHAR(64) PRIMARY KEY,
    asset_id VARCHAR(32) REFERENCES wells(asset_id),
    date DATE NOT NULL,
    agency VARCHAR(128) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    protocol_id VARCHAR(32), -- 'SR-01', 'SR-03', 'RC-02', etc.
    related_inspection_id VARCHAR(64),
    hours_to_report REAL,
    fine_usd REAL DEFAULT 0,
    status VARCHAR(32) NOT NULL, -- 'open' or 'closed'
    detail TEXT
);

-- 8. Document Sections (Reports & SOPs Vector Index)
CREATE TABLE document_sections (
    section_id SERIAL PRIMARY KEY,
    doc_type VARCHAR(32) NOT NULL, -- 'maintenance_report', 'manual', 'sop'
    doc_path VARCHAR(256) NOT NULL,
    asset_id VARCHAR(32),
    section_title VARCHAR(128),
    content TEXT NOT NULL,
    metadata JSONB NOT NULL,
    embedding vector(384) -- BAAI/bge-small-en-v1.5 via fastembed
);
CREATE INDEX ON document_sections USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_doc_asset ON document_sections (asset_id);

-- 9. Shared Context & Dynamic Overrides
CREATE TABLE shared_context (
    override_id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    author_user_id VARCHAR(32) REFERENCES fleet_users(user_id),
    scope VARCHAR(32) NOT NULL, -- 'inspection', 'asset', 'well_type', 'fleet'
    target_id VARCHAR(64) NOT NULL,
    override_type VARCHAR(32) NOT NULL,
    original_value JSONB,
    corrected_value JSONB NOT NULL,
    reason TEXT,
    valid_from DATE,
    valid_to DATE,
    is_confirmed BOOLEAN DEFAULT TRUE
);
```

---

## 4. LangGraph Agent State & Execution Graph

### 4.1 State Definition
```python
from typing import TypedDict, List, Dict, Any, Optional

class AgentState(TypedDict):
    user_id: str                      # Current active user (e.g. 'U-201')
    session_id: str                   # Active conversation ID
    user_query: str                   # Natural language question
    
    # Intent & Routing
    query_intent: str                 # 'single_well', 'downtime_ranking', 'spills', 'compliance', 'feedback'
    visual_preference: Optional[str]  # 'card', 'table', 'line', 'bar', 'map', 'heatmap', or None
    
    # Execution Context
    sql_query: Optional[str]
    sql_results: Optional[List[Dict[str, Any]]]
    retrieved_docs: Optional[List[Dict[str, Any]]]
    applied_overrides: Optional[List[Dict[str, Any]]]
    
    # Conflict & Grounding
    detected_conflicts: List[Dict[str, Any]]
    citations: List[str]
    
    # Output
    narrative_response: str
    generative_ui: Dict[str, Any]
```

### 4.2 State Machine Flow
```
[User Query + user_id]
         │
         ▼
[Node: LoadContext] ───► Read user session memory & active shared overrides
         │
         ▼
[Node: IntentRouter] ───► LiteLLM (Gemma 4) classifies query & extracts targets
         │
    ┌────┴──────────────────────────┐
    ▼                               ▼
[Node: ExecuteSQL]          [Node: RetrieveDocs]
(Quantitative / Time-series) (Narrative Reports / SOPs)
    │                               │
    └──────────────┬────────────────┘
                   │
                   ▼
       [Node: ConflictValidator]
       ( user conflicts)
                   │
                   ▼
       [Node: SynthesizeOpenUI]
       (Builds narrative text, citations, and OpenUI visual payload)
                   │
                   ▼
               [Finish]
```

---

## 5. Two-Level Memory & Feedback Data Flow

### 5.1 Shared Fleet Knowledge
When any user corrects raw data (Q12), updates an AI estimate (Q13), or specifies a new operational policy rule (Q14):
1. Written to `shared_context` with author attribution, original value, corrected value, and rationale.
2. In-memory override cache refreshed.
3. Subsequent analytical SQL and vector queries automatically join against active `shared_context` records.
4. **All other users** querying the affected asset or well type immediately receive the updated calculations and citations.

### 5.2 Private User Memory Isolation
When Michael Turner (`U-201`) asks about *"the three wells we discussed yesterday"* (Q11):
1. Handled via LangGraph's checkpointer keyed by `thread_id = f"{user_id}:{session_id}"`.
2. Conversation state preserves discussed entities (`WELL-0121`, `WELL-0138`, `WELL-0107`).
3. If Jessica Reed (`U-202`) asks the identical question (Q16), the checkpointer finds zero session state under `user_id = 'U-202'` and cleanly responds: *"I have no record of an earlier conversation with you on this topic."*

---

## 6. Generative UI Specification (OpenUI Contract)

Responses deliver a JSON payload containing `narrative` and `generative_ui`:

```json
{
  "narrative": "No, WELL-0001 is not producing oil. The latest inspection INS-0001-0203 on 15 Oct 2026 recorded a wellhead temperature only 3.2 °C above ambient, which is below the 15 °C T200 threshold...",
  "citations": [
    "INS-0001-0203",
    "CTX-0001-003",
    "OM-T200 §9.3"
  ],
  "generative_ui": {
    "component": "StatusCard",
    "props": {
      "asset_id": "WELL-0001",
      "name": "SW-23 Well 001",
      "well_type": "T200",
      "area": "Southwest Block 23",
      "is_producing": false,
      "delta_temp_c": 3.2,
      "ambient_temp_c": 19.2,
      "wellhead_temp_c": 22.4,
      "last_inspected_at": "2026-10-15T09:45:00Z",
      "inspector": "Ryan Brooks",
      "recorded_status": "active",
      "status_stale": true,
      "active_notes": [
        "Planned shut-in from 7 Oct for rod string replacement (CTX-0001-003)"
      ]
    }
  }
}
```

---

## 7. Phase-Gated Implementation Plan

### Phase 1: Environment & Storage Foundation
- Initialize Python project with `uv` (`pyproject.toml`).
- Create `docker-compose.yml` defining PostgreSQL 16 + `pgvector` container on port 5432.
- Write high-speed data ingestion pipeline loading all fleet and asset data into PostgreSQL.
- **Pytest Gate 1:** Verify row counts (200 wells, ~39.6k inspections, ~5.7k repairs) and schema constraints.

### Phase 2: Deterministic Domain Analytics & Pytest Suite
- Implement SQL analytical routines:
  - Production status evaluation per well type ($15^\circ\text{C}$ vs $20^\circ\text{C}$).
  - Downtime aggregator (7-day rule per non-producing inspection).
  - Spill filter with rainwater false-positive exclusion.
- **Pytest Gate 2:** Validate exact mathematical answers for Q1, Q2, Q4, Q5, Q6, Q7, Q8.

### Phase 3: Hybrid Search, LangGraph & DeepEval Evals
- Ingest maintenance reports and SOPs into `document_sections` with embeddings.
- Assemble LangGraph state machine with Gemma 4 (Google AI Studio) via LiteLLM.
- Implement shared memory and session memory checkpointers.
- **DeepEval Gate 3:** Run G-Eval rubrics for conflict detection (Q17, Q18), negative constraints (Q2), and citations (Q9, Q10).

### Phase 4: Full-Stack Generative UI & Dashboard
- Expose FastAPI streaming SSE endpoint.
- Connect React frontend with OpenUI rendering the 6 core widgets and dynamic layouts.
- User switcher (`U-101` through `U-402`) in UI.

### Phase 5: Test Dataset Readiness & Final Dry-Run
- Build the automated, single-command ingest script for the 2-hour final test dataset.
- Run complete regression benchmark across all 18 queries.

---

## 8. Benchmark Evaluation Reference (Q1 – Q18)

| Query ID | Test Focus | Expected Key Values & Ground Truth |
| :--- | :--- | :--- |
| **Q1** | Single Well Status | Not producing ($\Delta T = 3.2^\circ\text{C} < 15^\circ\text{C}$); Ryan Brooks; CTX-0001-003 shut-in; StatusCard visual. |
| **Q2** | Area Non-Producing | 4 wells (WELL-0164, 0170, 0172, 0175); State "No recorded reason" for 0164 and 0175 without hallucinating. |
| **Q3** | Trend Over Time | 13 weekly readings (23 Jul to 15 Oct 2026); Down on 8 Oct and 15 Oct; LineChart visual. |
| **Q4** | False Positive Handling | 6 real spills, 15.1 bbl; Exclude INS-0001-0070 rainwater false positive per CTX-0001-001. |
| **Q5** | Annual Downtime Calculation | Exactly 21 days (3 non-producing inspections in 2025: 24 Jul, 16 Oct, 23 Oct). |
| **Q6** | Downtime Ranking | Top 3: WELL-0121 (49d), WELL-0138 (42d), WELL-0107 (42d); BarChart visual. |
| **Q7** | Geospatial Spill Mapping | 4 wells in NE-08 with real spills in last 90 days (WELL-0151, 0165, 0175, 0186); Map visual. |
| **Q8** | 2D Spills Heatmap | Matrix of Areas $\times$ Months (Totals: SW-23: 35, SW-24: 43, NE-07: 37, NE-08: 26); Heatmap visual. |
| **Q9** | SOP Breaches & Compliance | 4 breaches on WELL-0001 (SR-01 late report, SR-02 containment > 4h, SR-03 open cleanup, RC-04 late response). |
| **Q10** | Unstructured Report Mining | Containment limit breaches in SW-24: WELL-0082 (7.1h) and WELL-0100 (8.1h) from report text. |
| **Q11** | Private User Session Memory | Michael Turner follows up on Q6 top 3 wells: WELL-0121 ($25,794), WELL-0138 ($46,942), WELL-0107 ($5,176). |
| **Q12** | Raw Data Correction | Michael Turner corrects INS-0164-0205 to 41.0°C; well becomes producing; flag inspector's conflicting note. |
| **Q13** | AI Estimate Correction | Correct WELL-0151 spill to 5.4 bbl; cascades to SR-01 reportable violation and 60d verification requirement. |
| **Q14** | Dynamic Policy Override | Michael Turner changes T350 RCA threshold to 2 repairs; adds WELL-0120; excludes T200 WELL-0102. |
| **Q15** | Global Propagation | Jessica Reed and Laura Simmons see Michael Turner's corrections from Q12 and Q13. |
| **Q16** | Multi-User Privacy Check | Jessica Reed asking for "three wells we discussed" receives no results from Michael Turner's session. |
| **Q17** | Data Conflict Honesty | Contradictions between Tyler Hughes's claims and 0.4°C thermal reading; flagged as unconfirmed. |
| **Q18** | Multi-User Conflict Honesty | Disagreement between Ryan Brooks and Chris Dalton on WELL-0101 spill; present both sources honestly. |
