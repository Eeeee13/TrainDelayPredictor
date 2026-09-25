import { create } from "zustand";
import {
  AlertEvent,
  DashboardFilters,
  KpiSnapshot,
  RouteDef,
  Vehicle
} from "@/domain/types";
import { liveFeed } from "@/mocks/liveFeed";

interface DashboardState {
  routes: RouteDef[];
  vehicles: Record<string, Vehicle>;
  alerts: AlertEvent[];
  selectedRouteId: string | null;
  selectedVehicleId: string | null;
  filters: DashboardFilters;
  kpi: KpiSnapshot;
  theme: "dark" | "light";

  init: () => () => void;
  selectVehicle: (id: string | null) => void;
  selectRoute: (id: string | null) => void;
  setFilters: (f: Partial<DashboardFilters>) => void;
  visibleVehicles: () => Vehicle[];
  toggleTheme: () => void;
}

function computeKpi(vehicles: Vehicle[], alertsCount: number): KpiSnapshot {
  if (vehicles.length === 0) {
    return { onTimePct: 100, atRiskPct: 0, avgPredictedDelaySec: 0, activeAlerts: 0 };
  }
  const atRisk = vehicles.filter((v) => v.risk !== "low").length;
  const avg =
    vehicles.reduce((sum, v) => sum + v.predictedDelaySeconds, 0) / vehicles.length;
  return {
    onTimePct: Math.round(((vehicles.length - atRisk) / vehicles.length) * 100),
    atRiskPct: Math.round((atRisk / vehicles.length) * 100),
    avgPredictedDelaySec: Math.round(avg),
    activeAlerts: alertsCount
  };
}

export const useDashboardStore = create<DashboardState>((set, get) => ({
  routes: liveFeed.routes,
  vehicles: {},
  alerts: [],
  selectedRouteId: null,
  selectedVehicleId: null,
  filters: { routeIds: null, depots: null, riskLevels: null },
  kpi: { onTimePct: 100, atRiskPct: 0, avgPredictedDelaySec: 0, activeAlerts: 0 },
  theme: "dark",

  init: () => {
    const unsubscribe = liveFeed.subscribe(({ vehicles, newAlerts }) => {
      set((state) => {
        const map: Record<string, Vehicle> = {};
        for (const v of vehicles) map[v.id] = v;
        const alerts = newAlerts.length
          ? [...newAlerts, ...state.alerts].slice(0, 40)
          : state.alerts;
        return {
          vehicles: map,
          alerts,
          kpi: computeKpi(vehicles, alerts.length)
        };
      });
    });
    return unsubscribe;
  },

  selectVehicle: (id) =>
    set((state) => ({
      selectedVehicleId: id,
      selectedRouteId: id
        ? state.vehicles[id]?.routeId ?? state.selectedRouteId
        : state.selectedRouteId
    })),

  selectRoute: (id) =>
    set((state) => ({
      selectedRouteId: id,
      selectedVehicleId:
        id && state.selectedVehicleId && state.vehicles[state.selectedVehicleId]?.routeId !== id
          ? null
          : state.selectedVehicleId
    })),

  setFilters: (f) => set((state) => ({ filters: { ...state.filters, ...f } })),

  visibleVehicles: () => {
    const { vehicles, filters, selectedRouteId } = get();
    return Object.values(vehicles).filter((v) => {
      if (selectedRouteId && v.routeId !== selectedRouteId) return false;
      if (filters.routeIds && !filters.routeIds.includes(v.routeId)) return false;
      if (filters.depots && !filters.depots.includes(v.depot)) return false;
      if (filters.riskLevels && !filters.riskLevels.includes(v.risk)) return false;
      return true;
    });
  },

  toggleTheme: () => set((state) => ({ theme: state.theme === "dark" ? "light" : "dark" }))
}));
