/**
 * Domain layer — pure types, no framework/UI dependencies.
 * Mirrors the backend contract described in the project's architecture doc
 * (NormalizedTelemetryRecord / ScheduleEntry / DelayPrediction), adapted
 * to what the dashboard actually renders. Kept separate from mock/UI code
 * so swapping the mock service for a real WebSocket client later only
 * touches `services/`, never the components.
 */

export type RiskLevel = "low" | "mid" | "high";

export interface LatLng {
  lat: number;
  lng: number;
}

export interface RoutePoint extends LatLng {
  /** Distance fraction [0..1] along the route polyline, precomputed for interpolation. */
  t: number;
}

export interface Stop {
  id: string;
  name: string;
  position: LatLng;
  /** Index of this stop within the route's stop sequence. */
  sequence: number;
}

export interface RouteDef {
  id: string;
  shortName: string; // e.g. "42"
  longName: string; // e.g. "Вокзал — Северный посёлок"
  color: string;
  path: RoutePoint[];
  stops: Stop[];
}

export interface ScheduleSample {
  /** Minutes since midnight. */
  t: number;
  planned: number; // planned offset (minutes from route start)
  actual: number; // actual offset (minutes from route start)
}

export interface Vehicle {
  id: string;
  routeId: string;
  garageNumber: string;
  position: LatLng;
  /** Heading in degrees, 0 = north, clockwise. */
  heading: number;
  speedKmh: number;
  /** Fraction along the route path [0..1]. */
  progress: number;
  delaySeconds: number; // current factual deviation (Matching Engine output)
  predictedDelaySeconds: number; // ML Inference output
  predictedHorizonMinutes: number;
  risk: RiskLevel;
  lastUpdate: number; // epoch ms
  depot: string;
  schedule: ScheduleSample[];
}

export interface AlertEvent {
  id: string;
  vehicleId: string;
  routeShortName: string;
  kind: "risk_increase" | "critical" | "recovered";
  message: string;
  timestamp: number;
}

export interface KpiSnapshot {
  onTimePct: number;
  atRiskPct: number;
  avgPredictedDelaySec: number;
  activeAlerts: number;
}

export interface DashboardFilters {
  routeIds: string[] | null; // null = all routes
  depots: string[] | null;
  riskLevels: RiskLevel[] | null;
}

export function riskFromDelaySeconds(sec: number): RiskLevel {
  const min = sec / 60;
  if (min < 2) return "low";
  if (min <= 5) return "mid";
  return "high";
}
