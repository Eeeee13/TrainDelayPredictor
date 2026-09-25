import { useMemo } from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { BusCard } from "./BusCard";

export function BusList() {
  const vehicles = useDashboardStore((s) => s.vehicles);
  const routes = useDashboardStore((s) => s.routes);
  const selectedRouteId = useDashboardStore((s) => s.selectedRouteId);
  const selectedVehicleId = useDashboardStore((s) => s.selectedVehicleId);
  const filters = useDashboardStore((s) => s.filters);
  const selectVehicle = useDashboardStore((s) => s.selectVehicle);

  const routeById = useMemo(() => new Map(routes.map((r) => [r.id, r])), [routes]);

  const list = useMemo(() => {
    return Object.values(vehicles)
      .filter((v) => {
        if (selectedRouteId && v.routeId !== selectedRouteId) return false;
        if (filters.riskLevels && !filters.riskLevels.includes(v.risk)) return false;
        if (filters.depots && !filters.depots.includes(v.depot)) return false;
        return true;
      })
      .sort((a, b) => b.predictedDelaySeconds - a.predictedDelaySeconds);
  }, [vehicles, selectedRouteId, filters]);

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
        {list.map((vehicle) => (
          <BusCard
            key={vehicle.id}
            vehicle={vehicle}
            route={routeById.get(vehicle.routeId)}
            selected={vehicle.id === selectedVehicleId}
            onSelect={() => selectVehicle(vehicle.id === selectedVehicleId ? null : vehicle.id)}
          />
        ))}
        {list.length === 0 && (
          <div className="text-sm text-base-400 dark:text-base-400 text-gray-600 px-3 py-6 text-center">
            Нет автобусов по текущим фильтрам
          </div>
        )}
      </div>
    </div>
  );
}
