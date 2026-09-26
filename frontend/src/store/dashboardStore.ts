import { create } from "zustand";
import type { DashboardFilters, KpiSnapshot, RouteDef, TrailPoint, Vehicle } from "@/domain/types";
import { fetchDashboard, subscribeRisks } from "@/services/dashboardApi";

const MAX_TRAIL_POINTS = 500;

const RISK_HYSTERESIS_SAMPLES = 1;

interface PendingRisk { level: Vehicle["risk"]; streak: number }

interface DashboardState {
  routes: RouteDef[];
  vehicles: Record<string, Vehicle>;
  riskTrails: Record<string, TrailPoint[]>;
  selectedVehicleId: string | null;
  filters: DashboardFilters;
  kpi: KpiSnapshot;
  status: "loading" | "online" | "error";
  error: string | null;
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
    const moved = !last || last.lat !== v.position.lat || last.lng !== v.position.lng;
    const extended = moved
      ? [...history, { lat: v.position.lat, lng: v.position.lng, risk: effectiveRisk }]
      : (last && last.risk !== effectiveRisk
          ? [...history.slice(0, -1), { ...last, risk: effectiveRisk }]
          : history);
    next[v.id] = extended.length > MAX_TRAIL_POINTS ? extended.slice(-MAX_TRAIL_POINTS) : extended;
  }
  for (const id of Object.keys(pendingRisk)) if (!seen.has(id)) delete pendingRisk[id];
  return next;
}

export const useDashboardStore = create<DashboardState>((set, get) => ({
  routes: [], vehicles: {}, riskTrails: {}, selectedVehicleId: null,
  filters: {routeIds: null, riskLevels: null, onlyPredicted: false, query: ""},
  kpi: {onTimePct: 0, atRiskPct: 0, avgPredictedDelaySec: 0, activeAlerts: 0},
  status: "loading", error: null,
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
  selectVehicle: (id) => set({selectedVehicleId: id}),
  setFilters: (f) => set(state => ({filters: {...state.filters, ...f}}))
}));