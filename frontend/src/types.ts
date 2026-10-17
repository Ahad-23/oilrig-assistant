/**
 * Type definitions for Asset Intelligence Copilot frontend.
 * Conforms to OpenUI generative UI specification.
 */

export interface FleetUser {
  user_id: string;
  name: string;
  role: string;
  team_id: string;
  team_name?: string;
  area_id?: string;
  area_name?: string;
}

export interface CitationItem {
  id: string;
  source_type: string;
  reference?: string;
}

export interface GenerativeUIPayload {
  component?: string; // 'StatusCard' | 'DataTable' | 'MetricLineChart' | 'ComparisonBarChart' | 'WellMap' | 'SpillHeatmap'
  type?: string;
  title?: string;
  props?: Record<string, any>;
  data?: Record<string, any>;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  citations?: CitationItem[];
  generative_ui?: GenerativeUIPayload | null;
  timestamp: string;
  statusUpdates?: string[];
  isStreaming?: boolean;
}

export interface AreaSummary {
  area_id: string;
  name: string;
  team_id: string;
  center_lat: number;
  center_lon: number;
  well_count: number;
}
