import { create } from "zustand";
import type { DashboardFilters, KpiSnapshot, LatLng, RouteDef, TrailPoint, Vehicle } from "@/domain/types";
import { fetchDashboard, subscribeRisks } from "@/services/dashboardApi";

const MAX_TRAIL_POINTS = 500;
const MAX_TRAIL_AGE_MS = 45 * 60 * 1000;
const MAX_PLAUSIBLE_SPEED_KMH = 140;

// noise guard
const RISK_HYSTERESIS_SAMPLES = 1;

interface PendingRisk { level: Vehicle["risk"]; streak: number }

interface DashboardState {
  routes: RouteDef[];
  vehicles: Record<string, Vehicle>;
  riskTrails: Record<string, TrailPoint[]>;
  selectedVehicleId: string | null;
  selectionToken: number;
  filters: DashboardFilters;
  kpi: KpiSnapshot;
  status: "loading" | "online" | "error";
  error: string | null;
  notificationsEnabled: boolean;
  toggleNotifications: () => void;
  init: () => () => void;
  refresh: () => Promise<void>;
  selectVehicle: (id: string | null) => void;
  setFilters: (f: Partial<DashboardFilters>) => void;
}

function computeKpi(vehicles: Vehicle[]): KpiSnapshot {
  const predicted = vehicles.filter(v => v.predictedDelaySeconds !== null);
  const atRisk = predicted.filter(v => v.risk === "medium" || v.risk === "high");
  return {
    onTimePct: predicted.length ? Math.round(100 * (predicted.length - atRisk.length) / predicted.length) : 0,
    atRiskPct: predicted.length ? Math.round(100 * atRisk.length / predicted.length) : 0,
    avgPredictedDelaySec: predicted.length ? Math.round(predicted.reduce((sum,v) => sum + (v.predictedDelaySeconds ?? 0), 0) / predicted.length) : 0,
    activeAlerts: atRisk.length
  };
}

function haversineKm(a: LatLng, b: LatLng): number {
  const R = 6371;
  const dLat = (b.lat - a.lat) * Math.PI / 180;
  const dLng = (b.lng - a.lng) * Math.PI / 180;
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * Math.PI / 180) * Math.cos(b.lat * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

// Pending hysteresis counters live outside the store's reactive state
const pendingRisk: Record<string, PendingRisk> = {};

function resolveEffectiveRisk(vehicleId: string, risk: Vehicle["risk"]): Vehicle["risk"] {
  if (RISK_HYSTERESIS_SAMPLES <= 1 || risk === "low" || risk === null) {
    delete pendingRisk[vehicleId];
    return risk;
  }
  const pending = pendingRisk[vehicleId];
  if (pending && pending.level === risk) {
    pending.streak += 1;
  } else {
    pendingRisk[vehicleId] = { level: risk, streak: 1 };
  }
  return pendingRisk[vehicleId].streak >= RISK_HYSTERESIS_SAMPLES ? risk : null;
}

function accumulateRiskTrails(prev: Record<string, TrailPoint[]>, vehicles: Vehicle[]): Record<string, TrailPoint[]> {
  const seen = new Set(vehicles.map(v => v.id));
  const next: Record<string, TrailPoint[]> = {};
  for (const v of vehicles) {
    const history = prev[v.id] ?? [];
    const last = history[history.length - 1];
    const effectiveRisk = resolveEffectiveRisk(v.id, v.risk);
    const now = Date.parse(v.lastUpdate) || Date.now();
    const moved = !last || last.lat !== v.position.lat || last.lng !== v.position.lng;

    let extended = history;
    if (moved) {
      let gap = false;
      if (last) {
        const elapsedH = Math.max((now - last.t) / 3_600_000, 1 / 3600); // guard against 0/negative clock skew
        const speedKmh = haversineKm(last, v.position) / elapsedH;
        gap = speedKmh > MAX_PLAUSIBLE_SPEED_KMH;
      }
      extended = [...history, { lat: v.position.lat, lng: v.position.lng, risk: effectiveRisk, t: now, gap }];
    } else if (last && last.risk !== effectiveRisk) {
      extended = [...history.slice(0, -1), { ...last, risk: effectiveRisk }];
    }

    const cutoff = now - MAX_TRAIL_AGE_MS;
    const aged = extended.filter(p => p.t >= cutoff);
    next[v.id] = aged.length > MAX_TRAIL_POINTS ? aged.slice(-MAX_TRAIL_POINTS) : aged;
  }
  // Drop hysteresis bookkeeping for vehicles that dropped out of the snapshot
  // so it can't grow unbounded over a long dispatcher shift.
  for (const id of Object.keys(pendingRisk)) if (!seen.has(id)) delete pendingRisk[id];
  return next;
}

export const useDashboardStore = create<DashboardState>((set, get) => ({
  routes: [], vehicles: {}, riskTrails: {}, selectedVehicleId: null, selectionToken: 0,
  filters: {routeIds: null, riskLevels: null, onlyPredicted: false, query: ""},
  kpi: {onTimePct: 0, atRiskPct: 0, avgPredictedDelaySec: 0, activeAlerts: 0},
  status: "loading", error: null, notificationsEnabled: true,
  refresh: async () => {
    try {
      const data = await fetchDashboard();
      set(state => ({routes: data.routes, vehicles: Object.fromEntries(data.vehicles.map(v => [v.id, v])),
        riskTrails: accumulateRiskTrails(state.riskTrails, data.vehicles),
        selectedVehicleId: state.selectedVehicleId && data.vehicles.some(v => v.id === state.selectedVehicleId)
          ? state.selectedVehicleId : null,
        kpi: computeKpi(data.vehicles), status: "online", error: null}));
    } catch (error) {
      set({status: "error", error: error instanceof Error ? error.message : "Ошибка подключения"});
    }
  },
  init: () => {
    void get().refresh();
    const timer = setInterval(() => { void get().refresh(); }, 10000);
    const unsubscribe = subscribeRisks(() => { void get().refresh(); });
    return () => {clearInterval(timer); unsubscribe();};
  },
  selectVehicle: (id) => set(state => ({selectedVehicleId: id, selectionToken: state.selectionToken + 1})),
  setFilters: (f) => set(state => ({filters: {...state.filters, ...f}})),
  toggleNotifications: () => set(state => ({notificationsEnabled: !state.notificationsEnabled}))
}));