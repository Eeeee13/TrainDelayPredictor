import { create } from "zustand";
import type { DashboardFilters, KpiSnapshot, RouteDef, Vehicle } from "@/domain/types";
import { fetchDashboard, subscribeRisks } from "@/services/dashboardApi";

interface DashboardState {
  routes: RouteDef[];
  vehicles: Record<string, Vehicle>;
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

export const useDashboardStore = create<DashboardState>((set, get) => ({
  routes: [], vehicles: {}, selectedVehicleId: null,
  filters: {routeIds: null, riskLevels: null, onlyPredicted: false, query: ""},
  kpi: {onTimePct: 0, atRiskPct: 0, avgPredictedDelaySec: 0, activeAlerts: 0},
  status: "loading", error: null,
  refresh: async () => {
    try {
      const data = await fetchDashboard();
      set(state => ({routes: data.routes, vehicles: Object.fromEntries(data.vehicles.map(v => [v.id, v])),
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
