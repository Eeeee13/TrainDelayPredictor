/**
 * Domain layer — pure types, no framework/UI dependencies.
 * Mirrors the backend contract described in the project's architecture doc
 * (NormalizedTelemetryRecord / ScheduleEntry / DelayPrediction), adapted
 * to what the dashboard actually renders. Kept separate from mock/UI code
 * so swapping the mock service for a real WebSocket client later only
 * touches `services/`, never the components.
 */

export type RiskLevel = "low" | "medium" | "high";

export interface LatLng {
  lat: number;
  lng: number;
}

export interface Stop {
  id: string;
  sequence: number;
  scheduledTime: string;
  position: LatLng
}

export interface RouteDef {
  id: string;
  vehicleId: string;
  shortName: string;
  stops: Stop[]
}

export interface RiskAssessment {
  vehicle_id: string;
  tr_id: number;
  target_stop_id: number;
  target_time_begin: string;
  predicted_at: string;
  predicted_delay_s: number;
  risk_level: RiskLevel;
  source: string;
}

export interface Vehicle {
  id: string;
  routeId: string;
  garageNumber: string;
  position: LatLng;
  trail: LatLng[];
  speedKmh: number;
  lastUpdate: string;
  delaySeconds: number | null;
  predictedDelaySeconds: number | null;
  risk: RiskLevel | null;
  targetStopId: string | null;
  targetTime: string | null;
  source: string | null;
}

export interface DashboardFilters {
  routeIds: string[] | null;
  riskLevels: RiskLevel[] | null;
  onlyPredicted: boolean;
  query: string;
}

export interface KpiSnapshot { onTimePct: number; atRiskPct: number; avgPredictedDelaySec: number; activeAlerts: number }
