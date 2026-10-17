import type { GenerativeUIPayload } from '../../types';
import { StatusCard } from './StatusCard';
import { DataTable } from './DataTable';
import { MetricLineChart } from './MetricLineChart';
import { ComparisonBarChart } from './ComparisonBarChart';
import { WellMap } from './WellMap';
import { SpillHeatmap } from './SpillHeatmap';
import { ConflictBanner } from './ConflictBanner';
import { DynamicShapeRenderer } from './DynamicShapeRenderer';

interface OpenUIRendererProps {
  payload: GenerativeUIPayload | null | undefined;
}

export const OpenUIRenderer: React.FC<OpenUIRendererProps> = ({ payload }) => {
  if (!payload) return null;

  const componentName = (payload.component || payload.type || "").toLowerCase();
  const rawProps = payload.props || (typeof payload.data === 'object' && !Array.isArray(payload.data) ? payload.data : {}) || {};
  const componentProps: any = {
    ...payload,
    ...rawProps,
    title: payload.title || rawProps.title || ""
  };

  // 1. Map / Geospatial Spill Pins (Highest priority when pins or lat/lon coordinates exist)
  if (
    componentName.includes("map") ||
    componentName.includes("geo") ||
    componentName.includes("pins") ||
    (Array.isArray(componentProps.pins) && componentProps.pins.length > 0) ||
    (Array.isArray(rawProps.pins) && rawProps.pins.length > 0) ||
    (Array.isArray(payload.props?.pins) && payload.props.pins.length > 0)
  ) {
    return <WellMap data={componentProps} />;
  }

  // 2. StatusCard / Single Well Health
  if (
    componentName.includes("status") ||
    componentName.includes("well_status") ||
    (componentName.includes("card") && (componentProps.wellhead_temp_c !== undefined || componentProps.delta_temp_c !== undefined))
  ) {
    return <StatusCard data={componentProps} />;
  }

  // 3. Line Chart / Time Series Trend
  if (
    componentName.includes("line") ||
    componentName.includes("trend") ||
    componentName.includes("timeseries") ||
    (componentName.includes("chart") && (componentProps.points || componentProps.records))
  ) {
    return <MetricLineChart data={componentProps} />;
  }

  // 4. Bar Chart / Rankings & Comparisons
  if (
    componentName.includes("bar") ||
    componentName.includes("ranking") ||
    componentName.includes("comparison")
  ) {
    return <ComparisonBarChart data={componentProps} />;
  }

  // 5. Heatmap / Area x Month Matrix
  if (
    componentName.includes("heat") ||
    componentName.includes("matrix") ||
    (componentProps.title && componentProps.title.toLowerCase().includes("heat")) ||
    (payload.title && payload.title.toLowerCase().includes("heat")) ||
    (Array.isArray(componentProps.rows) && componentProps.rows.some((r: any) => r && typeof r === 'object' && r.months)) ||
    (Array.isArray(payload.props?.rows) && payload.props.rows.some((r: any) => r && typeof r === 'object' && r.months))
  ) {
    return <SpillHeatmap data={componentProps} />;
  }

  // 6. Conflict / Contradiction Banner
  if (
    componentName.includes("conflict") ||
    componentName.includes("alert") ||
    componentName.includes("contradiction")
  ) {
    return <ConflictBanner data={componentProps} />;
  }

  // 7. Dynamic Shapes / Diagrams / Flow / Custom Visuals
  if (
    componentName.includes("shape") ||
    componentName.includes("diagram") ||
    componentName.includes("flow") ||
    componentName.includes("svg") ||
    componentName.includes("node") ||
    Array.isArray(componentProps.shapes) ||
    Array.isArray(componentProps.nodes) ||
    componentProps.svg
  ) {
    return <DynamicShapeRenderer data={componentProps} />;
  }

  // 8. Data Table / Listings
  if (
    componentName.includes("table") ||
    componentName.includes("list") ||
    Array.isArray(componentProps.rows) ||
    Array.isArray(componentProps.data) ||
    Array.isArray(componentProps)
  ) {
    return <DataTable data={Array.isArray(componentProps) ? { rows: componentProps } : componentProps} />;
  }

  // Fallback: DynamicShapeRenderer handles custom items, cards, or JSON display gracefully
  return <DynamicShapeRenderer data={componentProps} />;
};
